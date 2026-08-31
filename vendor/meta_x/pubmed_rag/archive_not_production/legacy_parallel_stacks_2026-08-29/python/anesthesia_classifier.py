"""
Anesthesia Classifier - Fixes FP audit with multi-stage classification
Stage 1: MeSH whitelist high precision
Stage 2: Title/abstract keyword rules + negative patterns
Stage 3: Embedding similarity to anesthesia centroid
Stage 4: Subdomain + StudyType classification with confidence
"""
import re
import logging
from typing import List, Dict, Tuple, Optional
from .models import PubMedArticle, Subdomain, StudyType
from .config import ANESTHESIA_MESH_WHITELIST, SUBDOMAIN_MESH_MAP, ANESTHESIA_SUBDOMAINS, STUDY_TYPES
import hashlib

logger = logging.getLogger(__name__)

# High precision title/abstract patterns for anesthesia core
ANESTHESIA_KEYWORDS = [
    r"\banesthesi",
    r"\banaesthesi",
    r"\bnerve block",
    r"\bspinal anesthesia",
    r"\bepidural",
    r"\bgeneral anesthesia",
    r"\bregional anesthesia",
    r"\bpropofol",
    r"\bsevoflurane",
    r"\bintubation",
    r"\bairway management",
    r"\bperioperative",
    r"\bpain management\b.*\bpostoperative",
    r"\bcritical care\b.*\bICU",
]
ANESTHESIA_REGEX = re.compile("|".join(ANESTHESIA_KEYWORDS), re.I)

# Negative patterns that indicate likely FP - paper mentions anesthesia only in passing
# FIX audit: classification FP
NEGATIVE_KEYWORDS = [
    r"\bdental",
    r"\bveterinary anesthesia\b",  # optional exclude depending on scope - keep but lower score
    r"\banesthesia was induced in mice",  # animal model non-clinical
]
NEGATIVE_REGEX = re.compile("|".join(NEGATIVE_KEYWORDS), re.I)

# Study type detection patterns
STUDY_TYPE_PATTERNS = {
    StudyType.randomized_controlled_trial: [
        r"\brandomized controlled trial\b", r"\bRCT\b", r"\brandomly assigned\b", r"\brandomised\b"
    ],
    StudyType.systematic_review: [
        r"\bsystematic review\b"
    ],
    StudyType.meta_analysis: [
        r"\bmeta.analysis\b", r"\bmeta analysis\b"
    ],
    StudyType.clinical_trial: [
        r"\bclinical trial\b", r"\bclinicaltrial\.gov\b"
    ],
    StudyType.observational_cohort: [
        r"\bcohort study\b", r"\bobservational study\b", r"\bprospective study\b", r"\bretrospective\b"
    ],
    StudyType.case_report: [
        r"\bcase report\b"
    ],
    StudyType.case_series: [
        r"\bcase series\b"
    ],
    StudyType.guideline: [
        r"\bguideline\b", r"\bpractice guideline\b", r"\bconsensus statement\b"
    ],
    StudyType.review: [
        r"\breview\b"
    ],
    StudyType.comparative_study: [
        r"\bcomparative study\b", r"\bcomparison\b.*\bstudy\b"
    ],
}

SUBDOMAIN_KEYWORDS = {
    Subdomain.regional: [r"\bregional anesthesia\b", r"\bnerve block\b", r"\bbrachial plexus\b", r"\bspinal\b.*\banesthesia\b", r"\bepidural\b", r"\bperipheral block\b"],
    Subdomain.pediatric: [r"\bpediatric\b", r"\bpaediatric\b", r"\bchildren\b", r"\bneonate\b", r"\binfant\b"],
    Subdomain.obstetric: [r"\bobstetric\b", r"\bpregnancy\b", r"\bcesarean\b", r"\blabor\b.*\banalgesia\b"],
    Subdomain.cardiac: [r"\bcardiac anesthesia\b", r"\bcardiothoracic\b", r"\bcardiopulmonary bypass\b", r"\bcardiac surgery\b"],
    Subdomain.pain: [r"\bchronic pain\b", r"\bacute pain\b", r"\bpain management\b", r"\bopioid\b.*\bpain\b"],
    Subdomain.critical_care: [r"\bICU\b", r"\bintensive care\b", r"\bcritical care\b", r"\bmechanical ventilation\b"],
    Subdomain.neuroanesthesia: [r"\bneuroanesthesia\b", r"\bneurosurgical\b", r"\bcraniotomy\b", r"\bbrain surgery\b"],
    Subdomain.airway: [r"\bairway\b", r"\bintubation\b", r"\blaryngoscopy\b", r"\bdifficult airway\b"],
    Subdomain.pharmacology: [r"\bpropofol\b", r"\bsevoflurane\b", r"\bpharmacokinetic\b", r"\banesthetic agent\b", r"\bdexmedetomidine\b"],
    Subdomain.general: [r"\bgeneral anesthesia\b", r"\binduction\b.*\banesthesia\b"],
    Subdomain.ambulatory: [r"\bambulatory\b", r"\boutpatient\b.*\banesthesia\b", r"\bday surgery\b"],
}

# Compile
SUBDOMAIN_REGEX = {k: re.compile("|".join(v), re.I) for k, v in SUBDOMAIN_KEYWORDS.items()}
STUDY_REGEX = {k: re.compile("|".join(v), re.I) for k, v in STUDY_TYPE_PATTERNS.items()}

class AnesthesiaClassifier:
    def __init__(self, embedding_engine=None):
        self.embedding_engine = embedding_engine
        # Pre-compute anesthesia centroid embedding for embedding-based FP filter (optional)
        self.anesthesia_centroid = None
        if embedding_engine:
            centroid_text = "anesthesia anesthesiology general anesthesia regional anesthesia spinal epidural nerve block propofol sevoflurane airway management perioperative pain ICU critical care"
            self.anesthesia_centroid = embedding_engine.embed_text(centroid_text)

    def is_anesthesia_core(self, article: PubMedArticle) -> Tuple[bool, float, List[str]]:
        """
        Multi-stage filter to reduce false positives - FIX audit critical.
        Returns (is_core, relevance_score, reasons)
        """
        reasons = []
        score = 0.0

        # Stage 1: MeSH whitelist = high precision
        if article.mesh_terms:
            overlap = set(article.mesh_terms) & ANESTHESIA_MESH_WHITELIST
            if overlap:
                score += 0.6
                reasons.append(f"MeSH whitelist hit: {', '.join(list(overlap)[:3])}")

        # Stage 2: Title/abstract regex
        text_to_check = f"{article.title} {article.abstract}".lower()
        if ANESTHESIA_REGEX.search(text_to_check):
            score += 0.3
            reasons.append("Title/abstract anesthesia keywords")

            # Count occurrences - more mentions = higher confidence
            matches = ANESTHESIA_REGEX.findall(text_to_check)
            if len(matches) >= 3:
                score += 0.2
            elif len(matches) >= 2:
                score += 0.1
        else:
            # No anesthesia keywords at all -> likely FP
            reasons.append("No anesthesia keywords in title/abstract")
            # Even if MeSH hit, if no keyword, reduce but not fail yet

        # Journal heuristic: anesthesia journals high precision
        if article.journal:
            anesth_journals = ["anesthesiology", "anesthesia & analgesia", "british journal of anaesthesia", "anaesthesia", "acta anaesthesiologica", "journal of clinical anesthesia", "regional anesthesia", "pain"]
            jl = article.journal.lower()
            if any(j in jl for j in anesth_journals):
                score += 0.3
                reasons.append(f"Anesthesia journal: {article.journal}")

        # PubTypes high precision
        if article.pub_types:
            # Publication types containing anesthesia are strong signals (mapped from MeSH? but keep)
            pass

        # Negative patterns - reduce score
        if NEGATIVE_REGEX.search(text_to_check):
            score -= 0.2
            reasons.append("Negative pattern found (possible FP)")

        # Stage 3: embedding similarity if available
        if self.anesthesia_centroid and self.embedding_engine:
            try:
                # embed title+abstract
                emb = self.embedding_engine.embed_text(f"{article.title} {article.abstract[:2000]}")
                sim = self.embedding_engine.cosine_similarity(emb, self.anesthesia_centroid)
                score = 0.6 * score + 0.4 * sim  # blend
                reasons.append(f"Embedding similarity to anesthesia centroid: {sim:.3f}")
                if sim < 0.25:
                    reasons.append("Low embedding similarity -> marginal")
            except Exception as e:
                logger.warning(f"Embedding similarity failed: {e}")

        # Threshold - tune to reduce FP while maintaining recall
        is_core = score >= 0.35  # threshold from config
        if not is_core:
            reasons.append(f"Score {score:.3f} below threshold 0.35 -> filtered as FP")

        # Clamp
        score = max(0.0, min(1.0, score))
        return is_core, score, reasons

    def classify_subdomain(self, article: PubMedArticle) -> Tuple[Subdomain, float, Dict[str, float]]:
        """Classify subdomain with confidence scores"""
        text = f"{article.title} {article.abstract}".lower()
        scores: Dict[str, float] = {}

        for sub, regex in SUBDOMAIN_REGEX.items():
            # Keyword count
            matches = regex.findall(text)
            kw_score = min(len(matches) * 0.3, 1.0)

            # MeSH boost
            mesh_score = 0.0
            if article.mesh_terms:
                mesh_overlap = set(article.mesh_terms) & SUBDOMAIN_MESH_MAP.get(sub.value, set())
                if mesh_overlap:
                    mesh_score = 0.5 + 0.1 * len(mesh_overlap)

            combined = 0.6 * kw_score + 0.4 * mesh_score
            scores[sub.value] = combined

        # General fallback if nothing strong
        if not scores or max(scores.values()) < 0.2:
            # Check general anesthesia keywords
            scores[Subdomain.general.value] = scores.get(Subdomain.general.value, 0.0) + 0.2

        # Pick max
        if scores:
            best_sub = max(scores, key=lambda k: scores[k])
            best_score = scores[best_sub]
            if best_score < 0.25:
                return Subdomain.other, best_score, scores
            return Subdomain(best_sub), best_score, scores
        return Subdomain.other, 0.0, scores

    def classify_study_type(self, article: PubMedArticle) -> Tuple[StudyType, float]:
        """Classify study type from PubTypes + title/abstract"""
        text = f"{article.title} {article.abstract}".lower()
        # First check PubTypes - authoritative
        pub_types_lower = [pt.lower() for pt in article.pub_types]

        # Mapping from PubMed pub types
        pubtype_map = {
            "randomized controlled trial": StudyType.randomized_controlled_trial,
            "systematic review": StudyType.systematic_review,
            "meta-analysis": StudyType.meta_analysis,
            "clinical trial": StudyType.clinical_trial,
            "observational study": StudyType.observational_cohort,
            "comparative study": StudyType.comparative_study,
            "case reports": StudyType.case_report,
            "case report": StudyType.case_report,
            "guideline": StudyType.guideline,
            "practice guideline": StudyType.guideline,
            "review": StudyType.review,
            "editorial": StudyType.editorial,
        }

        for pt in pub_types_lower:
            for key, st in pubtype_map.items():
                if key in pt:
                    return st, 0.9  # high confidence from PubType

        # Fallback to regex patterns on text
        for st, regex in STUDY_REGEX.items():
            if regex.search(text):
                # Confidence based on match in title higher
                if regex.search(article.title.lower()):
                    return st, 0.7
                return st, 0.5

        return StudyType.other, 0.1

    def classify(self, article: PubMedArticle) -> PubMedArticle:
        """Full classification pipeline"""
        is_core, relevance, reasons = self.is_anesthesia_core(article)
        subdomain, sub_conf, sub_scores = self.classify_subdomain(article)
        study_type, study_conf = self.classify_study_type(article)

        article.is_anesthesia_core = is_core
        article.anesthesia_relevance_score = relevance
        article.classification_reasons = reasons
        article.subdomain = subdomain
        article.subdomain_confidence = sub_conf
        article.subdomain_all_scores = sub_scores
        article.study_type = study_type
        article.study_type_confidence = study_conf

        return article

    def classify_batch(self, articles: List[PubMedArticle]) -> List[PubMedArticle]:
        return [self.classify(a) for a in articles]
