# Reviewer Stopping Rule v0.1

Experimental default: stop ordinary review when all are true:
1. latest independent reviewer contributes <2% newly accepted semantic units on calibration window;
2. no new E3/E4 defect family found;
3. residual census has no unexplained material region;
4. feature-specific gates pass;
5. role benchmark thresholds are satisfied.

This is not a completeness proof. Threshold must be calibrated in EXP-012.
