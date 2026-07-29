from assistant.infrastructure.vector_store import InMemoryVectorEntry, VectorRecord

# Deliberately small, manually curated fixture data. It validates retrieval wiring and is
# not an ingestion or embedding-generation pipeline.
SEED_VECTOR_ENTRIES = (
    InMemoryVectorEntry(
        record=VectorRecord(
            chunk_id="discovery-workshop-1",
            document_id="discovery-workshops",
            document_title="Discovery Workshops",
            content=(
                "A discovery workshop aligns stakeholders on business goals, user needs, "
                "constraints, and measurable outcomes before delivery begins."
            ),
            score=0.0,
        ),
        embedding=(1.0, 0.0, 0.0),
    ),
    InMemoryVectorEntry(
        record=VectorRecord(
            chunk_id="research-interviews-1",
            document_id="research-interviews",
            document_title="Stakeholder Interviews",
            content=(
                "Stakeholder interviews uncover assumptions, decision criteria, risks, "
                "and areas where teams disagree."
            ),
            score=0.0,
        ),
        embedding=(0.0, 1.0, 0.0),
    ),
    InMemoryVectorEntry(
        record=VectorRecord(
            chunk_id="success-measures-1",
            document_id="success-measures",
            document_title="Defining Success Measures",
            content=(
                "Useful success measures connect a user or business outcome to an observable "
                "metric and a target timeframe."
            ),
            score=0.0,
        ),
        embedding=(0.0, 0.0, 1.0),
    ),
)
