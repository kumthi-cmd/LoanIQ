"""LoanIQ back-end package.

BUSINESS: everything the desk's screens need from the server lives under app/:
  the synthetic loan tape generator now, and the loan API later in Step 1.
TECH: this file makes app/ a Python package, so modules run as
  `python -m app.loan_tape_gen` from backend/ and tests import `app.loan_tape_gen`.
"""
