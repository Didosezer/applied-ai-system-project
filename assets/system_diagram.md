# PawPal+ System Architecture

> Copy the Mermaid code below into https://mermaid.live, export as PNG, and save as `assets/system_diagram.png`.

```mermaid
flowchart TD
    subgraph UI["Streamlit UI — app.py"]
        A([User: natural language input])
        B([Sidebar: Owner / Pet setup\nbreed · birth date · neuter record])
        TAB1([Tab 1: Tasks\nAI input · schedule · Done buttons])
        TAB2([Tab 2: Pet Profiles\nbreed · age · neuter · vaccinations])
        R([Task review panel\nname · date · time · duration — all editable\nper-task Approve / Reject])
    end

    subgraph AGENT["agents/agent_orchestrator.py"]
        C[Build system prompt\nowner context + pet profiles + schedule]
        D[GPT-4o-mini\nfunction calling loop — max 6 iterations]
        E{tool_calls?}
    end

    subgraph TOOLS["tools/"]
        RAG["rag_retrieval.py\nrag_search(query)\nChromaDB · all-MiniLM-L6-v2\nKNOWLEDGE BASE RESULT only"]
        F["pawpal_wrapper.py\ncreate_tasks() → staged\ncommit_staged_tasks() → write"]
        G["storage.py\nsave_owner() / load_owner()\ndata/owners/*.json"]
    end

    subgraph KB["data/knowledge_base/"]
        KBC["core_knowledge_base.md\nBreed care · Toxic foods\nVaccination · Surgery\nDental · Parasites · Nails"]
    end

    subgraph VALIDATOR["evaluators/schedule_validator.py — always-on"]
        H["Rule layer  always enabled\nSame-pet time overlap → HIGH\nCross-pet conflict → MEDIUM"]
        I["AI layer  always enabled\nGPT semantic check\nfasting · surgery · medication timing\nexercise after surgery · toxic food combos"]
    end

    subgraph DATA["pawpal_system.py"]
        J["Owner → Pet → Task\nNeuterRecord\nVaccinationRecord\nage_display()"]
    end

    subgraph STORAGE["data/owners/"]
        K[("*.json\nauto-saved on every mutation")]
    end

    subgraph TESTS["tests/"]
        T1[test_pawpal.py]
        T2[test_pawpal_wrapper.py]
        T3[test_rag_retrieval.py]
        T4[test_schedule_validator.py]
        T5[test_agent_orchestrator.py\nall mocked — no API key]
    end

    A --> C
    B --> J
    C --> D
    D --> E
    E -- "rag_search" --> RAG
    RAG <--> KBC
    RAG -- "KB result only" --> D
    E -- "create_tasks" --> F
    F -- "staged tasks" --> H
    F -- "staged tasks" --> I
    H --> R
    I --> R
    R -- "Human: Approve ✅\nper-task or Approve All" --> F
    R -- "Human: Reject ❌" --> A
    F -- "commit" --> J
    J --> G
    G --> K
    K -- "load on startup" --> J
    J --> TAB1
    J --> TAB2
    TAB1 -- "mark Done\ncategory=vaccination\n→ auto VaccinationRecord" --> J
    D -- "stop: explanation" --> R

    style R fill:#fff9c4,stroke:#f9a825,color:#000
    style RAG fill:#e3f2fd,stroke:#1565c0,color:#000
    style KBC fill:#e3f2fd,stroke:#1565c0,color:#000
    style T1 fill:#e8f5e9,stroke:#388e3c,color:#000
    style T2 fill:#e8f5e9,stroke:#388e3c,color:#000
    style T3 fill:#e8f5e9,stroke:#388e3c,color:#000
    style T4 fill:#e8f5e9,stroke:#388e3c,color:#000
    style T5 fill:#e8f5e9,stroke:#388e3c,color:#000
```

## Component Summary

| Component | File | Role |
|---|---|---|
| UI | `app.py` | Streamlit — sidebar setup, Tasks tab, Pet Profiles tab |
| Agent | `agents/agent_orchestrator.py` | GPT-4o-mini function calling loop, system prompt with RAG + task rules |
| RAG | `tools/rag_retrieval.py` | ChromaDB vector search — strictly constrains AI to KB content only |
| Knowledge Base | `data/knowledge_base/core_knowledge_base.md` | Breed care, toxic foods, vaccination, surgery, dental, parasites, nails |
| Wrapper | `tools/pawpal_wrapper.py` | Staging bridge — tasks only committed after human approval |
| Validator | `evaluators/schedule_validator.py` | Rule layer (time overlap) + AI layer (GPT semantic conflicts) — both always enabled |
| Storage | `tools/storage.py` | JSON persistence — auto-saved on every mutation |
| Data Model | `pawpal_system.py` | Owner / Pet / Task / NeuterRecord / VaccinationRecord |
| Tests | `tests/` | All agent tests mocked — no API key required for CI |
