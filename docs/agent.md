# Triage agent

Outer graph: load the tenant's context, then run the agent.

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	load_tenant(load_tenant)
	agent(agent)
	__end__([<p>__end__</p>]):::last
	__start__ --> load_tenant;
	load_tenant --> agent;
	agent --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

Inside the `agent` node: a `create_agent` loop over search_policies, check_open_tickets and create_ticket, ending in a TriageResult.

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	model(model)
	tools(tools)
	__end__([<p>__end__</p>]):::last
	__start__ --> model;
	model -.-> __end__;
	model -.-> tools;
	tools -.-> __end__;
	tools -.-> model;
	model -.-> model;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```
