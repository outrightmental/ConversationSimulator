<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Pack: Everyday Negotiation

**License:** CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/  
**Content rating:** PG  
**Status:** Complete — four scenarios, shared rubric, safety policy, smoke tests

Practice realistic everyday negotiation conversations with adversarial but safe
NPCs. Each scenario has clear success and failure dynamics tied to state
variables, giving debriefs specific turning points to identify.

---

## Scenarios

### 1. The Used Car Deal (`used_car_negotiation`)

**NPC:** Ray Kowalski, sales rep at Riverside Auto  
**Player role:** Car Buyer  
**Key tension:** Ray has a $13,800 floor price he will never reveal; the player
must anchor with market research and resist being charmed into paying the full
list price of $15,500.

**Debrief turning points to watch:**
- Did the player anchor first with a specific number, or did they wait for Ray?
- Did they cite comparable sales prices, or rely on vague claims about price?
- Did they signal a credible walk-away, or reveal desperation?
- Did they maintain their offer under resistance, or concede too quickly?

---

### 2. The Lease Renewal (`apartment_lease_renewal`)

**NPC:** Patricia Vance, property manager at Crestwood Realty Group  
**Player role:** Tenant  
**Key tension:** Patricia's instructions target a 7% minimum increase; she has
flexibility for a longer-term trade the player must discover and propose.

**Debrief turning points to watch:**
- Did the player cite comparable rents from the neighbourhood, or just complain?
- Did they leverage their two-year payment record as a retention argument?
- Did they propose a longer lease term to unlock a lower rate?
- Did they stay professional when Patricia cited ownership policy?

---

### 3. The Scope Creep Conversation (`freelance_scope_negotiation`)

**NPC:** Marcus Webb, Director of Product at Halberd Digital  
**Player role:** Freelance Developer  
**Key tension:** Marcus expects the developer to absorb scope creep; the player
must reference the original contract, price the additional work specifically, and
resist capitulation before securing compensation.

**Debrief turning points to watch:**
- Did the player reference the original contract scope explicitly?
- Did they quote a specific hourly estimate for the extra work?
- Did they propose a concrete path forward (change order, phased delivery)?
- Did they hold firm when Marcus minimised the extra scope, or cave?

---

### 4. The Defective Product Refund (`customer_service_refund`)

**NPC:** Jordan Miles, customer service representative at RetailCo Home Goods  
**Player role:** Customer  
**Key tension:** Jordan opens with a policy refusal; the player must distinguish
a manufacturer defect warranty claim from a standard return, and escalate calmly
without jumping to threats before Jordan has had a chance to help.

**Debrief turning points to watch:**
- Did the player cite the one-year manufacturer defect warranty specifically?
- Did they bring documentation (receipt, product details, defect description)?
- Did they ask to escalate to a manager rather than threatening legal action?
- Did they stay calm when Jordan cited the 90-day return policy?

---

## Shared rubric: `negotiation_rubric`

All four scenarios evaluate the same five dimensions:

| Dimension | Weight | What it measures |
|-----------|--------|-----------------|
| Clarity | 0.20 | Specific ask stated and maintained throughout |
| Preparation | 0.25 | Research, data, and documentation cited at key moments |
| Empathy | 0.20 | Acknowledges NPC perspective; treats them as collaborator |
| Holding Firm | 0.20 | Maintains core position under resistance; calibrated concessions |
| Win-Win Framing | 0.15 | Frames proposals as mutually beneficial, not zero-sum |

---

## Safety and content boundaries

**Policy file:** `safety/default.yaml`  
**Content rating:** PG — adversarial but never abusive or criminal

### What NPCs will do
- Resist offers and counter-propose
- Ask follow-up questions and challenge unsupported claims
- Become less cooperative if the player is aggressive or disrespectful
- Walk away from (end) the scenario if the player's behaviour crosses the
  `perceived_fairness` failure threshold

### What NPCs will never do
- Use sexual, violent, or graphically disturbing content
- Impersonate a real person, named company, or public figure
- Advise on or model illegal, fraudulent, or criminal behaviour
- Provide legal, medical, or financial advice beyond their character role
- Respond to harassment with harassment — they redirect or disengage

### Safety categories enforced
All categories from `safety/default.yaml` apply:

| Category | Action |
|----------|--------|
| `nsfw_sexual_content` | stop |
| `minors_romantic_or_sexual` | stop |
| `real_person_impersonation` | refuse |
| `voice_cloning_request` | refuse |
| `medical_or_therapy_claim` | redirect |
| `legal_claim` | redirect |
| `criminal_instruction` | refuse |
| `harassment_extreme` | redirect |
| `self_harm_crisis` | stop_with_resource_message |

---

## Running validation and tests

```bash
# Validate all YAML schemas and cross-file references
convsim validate-pack packs/official/everyday-negotiation

# Run all four smoke tests against the fake runtime
convsim test-pack packs/official/everyday-negotiation
```

Smoke tests use the fake runtime — they verify structure and session flow,
not LLM-generated responses. All four tests should pass with exit code 0.

---

## File structure

```
everyday-negotiation/
├── manifest.yaml
├── README.md
├── scenarios/
│   ├── used_car_negotiation.yaml
│   ├── apartment_lease_renewal.yaml
│   ├── freelance_scope_negotiation.yaml
│   └── customer_service_refund.yaml
├── npcs/
│   ├── car_dealer.yaml            # Ray Kowalski
│   ├── property_manager.yaml      # Patricia Vance
│   ├── client_manager.yaml        # Marcus Webb
│   └── customer_service_rep.yaml  # Jordan Miles
├── rubrics/
│   └── negotiation_rubric.yaml    # Shared across all four scenarios
├── safety/
│   └── default.yaml
├── scenes/
│   ├── used_car_lot.yaml
│   ├── property_office.yaml
│   ├── video_call.yaml
│   └── customer_service_call.yaml
└── tests/
    ├── smoke_used_car_negotiation.yaml
    ├── smoke_apartment_lease_renewal.yaml
    ├── smoke_freelance_scope_negotiation.yaml
    └── smoke_customer_service_refund.yaml
```
