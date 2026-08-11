# Three-way match exception report

**Shipment** SHP-4471 &nbsp;&nbsp; **Contract** PAE-2611 &nbsp;&nbsp; **Status** PAYMENT BLOCKED

- Rules evaluated: 16
- Exceptions: 9 (7 blocking)
- Confirmed recoverable: USD 95,175.85
- Pending human review: USD 89,118.75

| Rule | Check | Layer | Outcome | Min conf | Impact USD |
|---|---|---|---|---|---|
| DOC-01 | Required document set is complete | deterministic | **FAIL** | - |  |
| FIN-01 | Moisture allowance reflected on invoice | deterministic | **FAIL** | 0.95 | 95,175.85 |
| FIN-03 | Invoice weight basis matches contract weight basis | deterministic | **FAIL** | 0.91 |  |
| SHP-01 | Shipment effected within contractual window | deterministic | **FAIL** | 0.98 |  |
| CPT-01 | Counterparty identity consistent across documents | model-assisted | **REVIEW** | 0.93 |  |
| FIN-02 | Oil content discount reflected on invoice | deterministic | **REVIEW** | 0.86 | 89,118.75 |
| QUA-02 | Oil content meets contractual minimum | deterministic | **REVIEW** | 0.86 |  |
| SHP-02 | Authority to amend the shipment window | human-authority | **REVIEW** | 0.72 |  |
| QUA-01 | Moisture within specification or allowance band | deterministic | **ALLOW** | 0.97 |  |
| PRC-01 | Invoiced unit price matches contract price | deterministic | **PASS** | 0.98 |  |
| PRC-02 | Invoice line extension arithmetic | deterministic | **PASS** | 0.99 |  |
| PRC-03 | Contract price derives correctly from futures and basis | deterministic | **PASS** | 0.96 |  |
| QTY-01 | Shipped weight within contract tolerance | deterministic | **PASS** | 0.99 |  |
| QTY-02 | Invoiced quantity matches bill of lading | deterministic | **PASS** | 0.99 |  |
| QUA-03 | Foreign matter and damaged grain caps | deterministic | **PASS** | 0.96 |  |
| QUA-04 | Protein meets contractual minimum | deterministic | **PASS** | 0.97 |  |
