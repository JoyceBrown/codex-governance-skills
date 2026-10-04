# HCR Module Boundaries

HCR keeps one authority while grouping its internal work into five bounded
modules. These names describe maintenance ownership; they are not separate
skills, services, ledgers, or invocation steps.

| Module | May do | Must not do |
| --- | --- | --- |
| `gate-core` | Own authorization, target identity, rollback, action status, and completion claims. | Delegate permission, rewrite project facts, or accept a child result as completion. |
| `cognitive-mode` | Label WHY/WHAT/HOW evidence and propose a bounded next check. | Change requirements, authorize a mutation, or promote an assumption to fact. |
| `replay` | Read an authorized historical projection and return candidate matches with evidence references. | Call an LLM, write project truth, grant permission, or claim a live result. |
| `experience-store` | Store redacted candidates and perform explicit review or expiry transitions. | Become a second ledger, infer authorization, or overwrite current project state. |
| `ledger-bridge` | Copy verified gate/checkpoint metadata into the existing durable ledger through its owner. | Create a ledger, change requirements, or become an independent source of truth. |

Dependencies point toward `gate-core`: cognitive and replay modules propose
evidence; the gate decides. The experience store and ledger bridge remain
append-only or delegated projections. A missing module degrades to the local
gate and current evidence; it never creates a replacement runtime.
