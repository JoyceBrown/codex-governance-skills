# Third-Party Skill and Plugin Safety

Skills and plugins are executable policy: their Markdown can change agent behavior, and their scripts can access files, processes, credentials, and networks.

Before borrowing or installing a third-party skill:

1. Check repository owner, maintenance activity, license, and pinned commit.
2. Read all `SKILL.md`, hooks, scripts, manifests, and install instructions.
3. Search for network calls, credential reads, broad filesystem access, shell execution, hidden HTML comments, encoded payloads, and automatic writes to global rules.
4. Copy concepts, not whole frameworks. Remove unnecessary dependencies and permissions.
5. Test in an isolated directory with a non-production profile.
6. Keep an inventory of the borrowed source and the reason each piece exists.
7. Never allow an imported skill to auto-promote memory, modify core instructions, or publish/deploy without a separate authorization gate.

Popularity and star count are discovery signals, not security or correctness evidence.
