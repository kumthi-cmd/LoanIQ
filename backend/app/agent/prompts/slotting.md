Product Slotting has run on this tape. Its columns on `loans`:
- deliverable: TRUE if an agency pool takes the loan. not_slotted_reason says why not: 'No agency pool' (Jumbo, Non-QM), 'No TBA product' (ARMs), 'Delinquent'.
- agency ('UMBS' or 'GNMA II'), slot (e.g. 'UMBS 30Y 2.5 / 3.0'), down_coupon and up_coupon (percent): set only when deliverable.
- spec_stories (text, e.g. 'LLB 275K, NY'; 'Generic TBA' if none), llb_tier (the loan's lowest LLB tier cap in dollars, e.g. 85000), and one TRUE/FALSE column per story: story_llb, story_ny, story_pr, story_low_fico.
- A loan can carry several stories but goes into one pool, so never add story counts together as if they were loans.
- For why one loan is or is not slotted, call explain_slot; do not guess from the columns.
