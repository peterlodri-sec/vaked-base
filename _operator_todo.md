# _operator_todo: Researcher Outreach (5 Key Contacts)

**Target:** Early feedback from leading researchers before arxiv submission  
**Timeline:** Send after PR #103 finalized + arxiv preprint ready (2-3 weeks)  
**Goal:** Validate research direction, identify collaboration opportunities, improve visibility

---

## Contact 1: Mark S. Miller (Google / Agoric)

**Role:** Pioneer of object capabilities and POLA  
**Relevant Project:** E language, Agoric (JavaScript-based capability systems)  
**Research Area:** Robust composition, ambient authority elimination  

### Personalized Questions

**Q1 (Soundness):**
> "In E and your object-capability work, authority flows through unforgeable references at runtime. We move POLA verification to compile-time via typing rules (§4 of 0011-type-system.md). Do you see this as complementary (static proof + runtime enforcement) or does compile-time checking risk missing runtime complications we haven't modeled?"

**Q2 (Real-World Patterns):**
> "From your experience with Agoric systems, which POLA violation patterns are most common in practice? We've identified amplification (delegating more than held) and transitive overreach; are there failure modes our typed model should explicitly address?"

### Email Hook
```
"Your foundational work on object capabilities inspired our approach to POLA as a typing rule. 
We'd value your perspective on whether compile-time verification can catch the real-world 
authority mistakes you've observed in deployed capability systems."
```

---

## Contact 2: Talia Ong (Mozilla Research / Nickel)

**Role:** Language design for configuration + contracts  
**Relevant Project:** Nickel language (structural typing, refinement contracts)  
**Research Area:** Configuration languages, contract systems, type-driven validation  

### Personalized Questions

**Q1 (Design Tradeoff):**
> "Nickel allows open predicates in contracts (Turing-complete validation). We close the constraint set for decidability. Have you encountered real-world configurations that *need* open predicates, or would a closed set (bounded regex, ranges, enums) have sufficed? This shapes our language-design roadmap."

**Q2 (Capability Extension):**
> "Vaked extends Nickel's structural typing with capability domains and partial orders. Could Nickel's contract system express capability attenuation (e.g., `fs.repo_ro <= fs.repo_rw`)? Would that be a natural extension, or does it clash with Nickel's philosophy?"

### Email Hook
```
"We built on Nickel's structural typing and contract philosophy, adding capability-aware 
constraints for agentic systems. Curious whether you see this as a natural evolution or 
whether it fundamentally conflicts with Nickel's design goals."
```

---

## Contact 3: Dominik Charousset (TU Berlin / CAF)

**Role:** Actor systems + distributed security  
**Relevant Project:** CAF (C++ Actor Framework), secure message passing  
**Research Area:** Actor models, distributed protocol security, membranes  

### Personalized Questions

**Q1 (Mesh Topology):**
> "Your CAF work on actor supervision and message routing is relevant to our 'mesh' topology (principal-to-principal delegation). We declare authority attenuation rules statically; CAF enforces at runtime via actors. How would you model capability flow in a CAF system? Should we think of each actor as a membrane?"

**Q2 (Protocol Matching):**
> "We're designing HCP/Litany (a capability-aware protocol, RFC 0001-0006). CAF uses message passing with implicit identity. Should capability grants be embedded in message headers, or should they be negotiated out-of-band? What's your experience with capability transport in CAF?"

### Email Hook
```
"CAF's work on distributed actor supervision and secure routing is directly relevant to 
our runtime architecture (Zig daemons + OTP). We're designing protocols for capability 
delegation; would value your thoughts on how capabilities fit into message-passing semantics."
```

---

## Contact 4: Daniel Fryer (UIUC / Capability Machines)

**Role:** Formal capability systems, hardware enforcement  
**Relevant Project:** Capability machines, CHERI, formal models  
**Research Area:** Capability-based security, formal verification, hardware-software co-design  

### Personalized Questions

**Q1 (Formal Proof):**
> "We have an informal soundness proof for POLA (§4.5 of 0011-type-system.md): attenuation order is a partial order, use-check prevents overage, delegation-check ensures monotone decrease. Have you found formal proof techniques that scale well to real type systems? We'd like to machine-check this in Coq/Lean for v1.0."

**Q2 (Hardware Relevance):**
> "CHERI brings capabilities to hardware. Our type system is software-only (no cryptographic proof of capabilities). How would you integrate a type-verified capability graph with CHERI's hardware enforcement? Is there a mismatch in threat models, or could they be complementary?"

### Email Hook
```
"Your work on formal capability models inspired our approach to POLA verification. 
We'd like to formally verify our type system soundness (machine-checked proof). 
What's your experience taking informal capability arguments to formal proofs?"
```

---

## Contact 5: Nadia Heninger (UPenn / Systems Security)

**Role:** Cryptography, systems security, reproducibility  
**Relevant Project:** Supply chain security, reproducible builds, deterministic systems  
**Research Area:** Verifiable infrastructure, cryptographic commitment to source, build reproducibility  

### Personalized Questions

**Q1 (Determinism for Trust):**
> "We guarantee deterministic lowering: identical inputs → byte-identical artifacts. Combined with flake.lock pinning, this enables reproducibility checks. Have you found deterministic compilation sufficient for supply-chain trust, or does it need cryptographic attestation (signed hashes)? Should we add signature verification to provenance?"

**Q2 (Auditability):**
> "Our provenance.json maps artifact regions back to source spans. This enables 'follow the artifact to the declaration that created it.' For supply-chain security, is source-level traceability enough, or do operators need cryptographic proof that the lowering was correct (e.g., a Merkle proof of the compilation)?"

### Email Hook
```
"Your work on reproducible infrastructure and deterministic builds aligns perfectly 
with our approach. We combine deterministic lowering + provenance tracking for auditable 
infrastructure-as-code. Would value your perspective on whether this addresses real 
supply-chain concerns or if we're missing a cryptographic layer."
```

---

## Template Email (Customize Per Researcher)

```
Subject: Vaked—Capability-Graph Language for Agentic Systems [RESEARCHER_NAME's work inspired us]

Hi [NAME],

We're publishing research on Vaked, a typed declarative language for agentic systems 
that statically verifies Principle of Least Privilege (POLA) via capability graphs.

Your work on [SPECIFIC CONTRIBUTION: object capabilities / structural typing / actor systems / 
formal verification / reproducible infrastructure] directly motivated our approach.

We'd value your feedback on two specific questions (see below). Paper draft + source code available 
in the links.

**Q1: [PERSONALIZED_QUESTION_1]**

**Q2: [PERSONALIZED_QUESTION_2]**

Paper: [arxiv or GitHub link]
Repo: https://github.com/peterlodri-sec/vaked-base
PR #103 (research roadmap): https://github.com/peterlodri-sec/vaked-base/pull/103

Early feedback would help us refine before arxiv submission (targeted Q3 2026).

Best regards,
[YOUR_NAME]
[YOUR_TITLE / AFFILIATION if applicable]
[YOUR_EMAIL]
```

---

## Outreach Checklist

### Pre-Send
- [ ] Verify researcher's current affiliation (Google Scholar / university faculty page)
- [ ] Find correct email (usually firstname@company or firstname@university)
- [ ] Read 1-2 recent papers by each researcher
- [ ] Customize questions (don't use template verbatim)
- [ ] Keep email < 250 words (shorter is better)
- [ ] Include 2-3 specific links (arxiv, PR, repo)
- [ ] Use your real name + email (builds credibility)

### Timing
- [ ] Wait until PR #103 is finalized (2-3 weeks from now)
- [ ] Have arxiv preprint link ready (not just draft)
- [ ] v0.1 release roadmap should be public (CHANGELOG.md)
- [ ] Send between 9-11 AM on weekday (higher response rate)
- [ ] Space emails by 2-3 days (don't spam all at once)

### Post-Send
- [ ] Add to calendar: 2-week follow-up if no response
- [ ] Log responses + feedback (maintain researcher relationship)
- [ ] If positive response: offer co-authorship, collaboration, or acknowledgment
- [ ] Share arxiv link + release announcement when live

---

## Response Scenarios

### If They Respond Positively
- Offer co-authorship on paper or future work
- Ask for introduction to collaborators in their field
- Invite them to review v0.2 compiler optimizations
- Propose joint publication (e.g., formal verification paper)

### If They Respond with Concerns
- Take feedback seriously; iterate on paper/design if valid
- Ask for specifics: "What would change your mind?"
- Propose follow-up call to dive deeper

### If No Response
- One polite follow-up after 2 weeks (not pushy)
- Don't take it personally; researchers are busy
- Watch for their next conference talks / papers
- Reach out again when v0.2 is released

---

## Alternative Contacts (If Primary 5 Don't Respond)

- **Max Willsey** (UW/egg-smyth) — Datalog for systems; ask about constraint optimization
- **Stephanie Weirich** (Penn) — Dependent types; ask about formalizing capability partial orders
- **Andrew Appel** (Princeton) — Program verification; ask about machine-checked proofs
- **Cormac Flanagan** (UCSC) — Information flow; ask about capability flow analysis
- **Sebastian Burckhardt** (MSR) — Distributed reproducibility; ask about supply-chain verification

---

## Next Steps

1. **Now:** Finalize PR #103 (this week)
2. **In 1 week:** Prepare arxiv submission + links
3. **In 2-3 weeks:** Send outreach emails (stagger by 2-3 days)
4. **In 3-4 weeks:** Respond to feedback, iterate on paper
5. **In 4-5 weeks:** Submit to arxiv
6. **In 5-6 weeks:** Release v0.1, announce in researcher communities

---

## Tracking

**Date Created:** 2026-06-13  
**Status:** Ready to send (pending arxiv preprint)  
**Responses Logged:** [To be updated]

| Researcher | Email Sent | Date | Response | Outcome |
|---|---|---|---|---|
| Mark Miller | — | — | — | — |
| Talia Ong | — | — | — | — |
| Dominik Charousset | — | — | — | — |
| Daniel Fryer | — | — | — | — |
| Nadia Heninger | — | — | — | — |

---

**Good luck! Remember: genuine questions + specific links = higher response rate.** 🎯
