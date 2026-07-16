# 04 — Representative Sampling Strategy

Type: grilling
Status: resolved
Blocked by: 02

## Question

How should we select the "representative task" set from the full corpus of sessions? Three sub-decisions need resolving:

1. **Clustering method**: k-means on embeddings vs. stratified sampling by taxonomy bucket vs. manual curation — what's right given the likely corpus size (tens to hundreds of sessions)?
2. **Balance target**: how many tasks per taxonomy bucket, and what's the total dataset size (e.g., 20 tasks? 50? 100?)
3. **Refresh policy**: does the dataset grow as new sessions are logged, or is it a one-time snapshot?

## Answer

### 1. Clustering Method
- **Decision**: Stratified sampling by category.
- **Rationale**: Given a corpus of ~160 sessions across 14 categories, stratified sampling provides a simple, accurate, and predictable way to cover all active areas without the complexity and overhead of k-means embeddings.

### 2. Balance Target
- **Decision**: Proportional to corpus volume, total 20 tasks.
- **Rationale**: A target of 20 tasks keeps the evaluation pipeline fast while proportional sampling ensures the benchmark focuses on high-frequency workflows (e.g., Trading, Rule Aggregation, Data Extraction) while preserving minimal representation for lower-frequency categories.

### 3. Refresh Policy
- **Decision**: Dynamic growth (dataset grows automatically when new sessions are logged).
- **Rationale**: The dataset should auto-incorporate new sessions to keep the benchmark aligned with evolving user workflows. This requires the pipeline to automatically parse and ingest newly logged sessions into the active task pool.
