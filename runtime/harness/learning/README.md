# Local preference learning

AI4HEOR may propose a reusable work preference only after the same pattern is
observed in at least two independent interactions. A proposal is not a rule.

Allowed examples include output language, preferred table layout, or a repeated
request to show a particular audit field. Proposals must not contain secrets,
patient-level data, confidential source content, substantive scientific choices,
or inferred sensitive attributes.

Only the researcher can accept a proposal into `preferences.json`. Accepted
preferences remain local and can be viewed, edited, disabled, or deleted. They
cannot weaken the harness, alter a calculation engine, create an approval, or
replace current task instructions.

The app records each acceptance, edit, state change, or deletion under
`reviews/` and binds the decision to the exact proposal and preference-store
hash. These records document a local Human assertion; they are not an external
identity signature.
