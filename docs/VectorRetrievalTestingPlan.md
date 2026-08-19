# Vector Retrieval Testing Dashboard — ✅ Finalized Plan

A dedicated debugging workspace to test and validate pgvector cosine similarity search end-to-end. You paste a query, click "Test Retrieval", and the dashboard shows you the exact chunks PostgreSQL returned — including similarity scores, titles, categories, content, and metadata — so you can verify that your vector math is working correctly.

## Decisions Locked In

| Decision | Choice |
|----------|--------|
| Embedding Model | `gemini-embedding-001` (3072-dim, already in use) ✅ |
| Top-K | **User-controlled slider** (range: 3–10, default: 5) ✅ |
| Auth | **JWT-protected** — placed as new nav item below Memory Bank ✅ |

## Embedding Model

> [!IMPORTANT]
> **Confirmed: `gemini-embedding-001`** — same model used for ingestion. The retrieval endpoint uses `task_type="retrieval_query"` (the paired counterpart to the stored `"retrieval_document"` task type). Zero LLM cost — no generation tokens used.
>
> - **For storage (ingestion):** `task_type="retrieval_document"` ✅ (already in use)
> - **For query (retrieval):** `task_type="retrieval_query"` ← this is the correct counterpart

> [!TIP]
> **Cheapest quota usage in Antigravity:** Use **`gemini-embedding-001`** (free tier, generous quota) for the embedding call. No LLM call is needed for the test endpoint — it is purely embed → SQL → return. Zero token cost on the generation side.

---

## Proposed Changes

### Backend — `AiCareerToolkitBE`

---

#### [MODIFY] [schemas.py](file:///home/danish-ansari/Desktop/ProjectDev/DanishDev&Projects/AiCareerToolkitBE/app/slices/memory/schemas.py)

Add two new Pydantic schemas:

- **`RetrievalTestRequest`** — receives the raw query string and optional `top_k` (default 5).
- **`RetrievalResultItem`** — represents a single matched chunk with its similarity score (`similarity_score: float`, computed as `1 - cosine_distance`).
- **`RetrievalTestResponse`** — wraps `list[RetrievalResultItem]` + `query` + `total_results`.

```python
class RetrievalTestRequest(BaseModel):
    query: str
    top_k: int = 5

class RetrievalResultItem(BaseModel):
    id: int
    title: Optional[str]
    category: str
    content: str
    similarity_score: float   # e.g. 0.89 → display as "89% Match"
    created_at: datetime
    class Config: from_attributes = True

class RetrievalTestResponse(BaseModel):
    query: str
    total_results: int
    results: list[RetrievalResultItem]
```

---

#### [MODIFY] [service.py](file:///home/danish-ansari/Desktop/ProjectDev/DanishDev&Projects/AiCareerToolkitBE/app/slices/memory/service.py)

Add a new public service function `test_retrieval_service`:

1. Call `_get_embedding(query, task_type="retrieval_query")` — same model, correct task type.
2. Run raw SQL using SQLAlchemy `text()`:
   ```sql
   SELECT id, title, category, content, created_at,
          1 - (embedding <=> :query_vec) AS similarity_score
   FROM career_memory
   ORDER BY embedding <=> :query_vec
   LIMIT :top_k;
   ```
3. Map rows → `list[RetrievalResultItem]`.
4. Return `RetrievalTestResponse`.

> [!NOTE]
> The `<=>` operator is **cosine distance** in pgvector. `1 - distance = cosine similarity`. A score of `0.89` means 89% semantic similarity.

---

#### [MODIFY] [router.py](file:///home/danish-ansari/Desktop/ProjectDev/DanishDev&Projects/AiCareerToolkitBE/app/slices/memory/router.py)

Add one new route:

```python
@router.post("/test-retrieval", response_model=RetrievalTestResponse)
def test_retrieval(
    request: RetrievalTestRequest,
    db: Session = Depends(get_db),
):
    """
    Dev/Debug endpoint: embed a query and return the top-K most
    semantically similar career memory chunks with cosine similarity scores.
    """
    return test_retrieval_service(request, db)
```

**Final URL:** `POST /api/v1/memory/test-retrieval`

> [!NOTE]
> No changes to `main.py` — the memory router is already registered. No new DB tables needed.

---

### Frontend — `AiCareerToolkitFE/aicareertoolkit-fe`

---

#### [MODIFY] [endpoints.ts](file:///home/danish-ansari/Desktop/ProjectDev/DanishDev&Projects/AiCareerToolkitFE/aicareertoolkit-fe/src/api/endpoints.ts)

Add `testRetrieval` to the `memory` object:

```ts
memory: {
  // ...existing...
  testRetrieval: '/api/v1/memory/test-retrieval',
}
```

---

#### [NEW] `src/types/retrieval.types.ts`

Typed interfaces mirroring the backend schemas:

```ts
export interface RetrievalResultItem {
  id: number
  title: string | null
  category: string
  content: string
  similarity_score: number   // 0.0 – 1.0
  created_at: string
}

export interface RetrievalTestResponse {
  query: string
  total_results: number
  results: RetrievalResultItem[]
}
```

---

#### [NEW] `src/api/services/retrieval.service.ts`

```ts
export async function testRetrieval(query: string, topK = 5): Promise<RetrievalTestResponse> {
  const { data } = await api.post<RetrievalTestResponse>(
    API_ENDPOINTS.memory.testRetrieval,
    { query, top_k: topK }
  )
  return data
}
```

---

#### [MODIFY] [paths.ts](file:///home/danish-ansari/Desktop/ProjectDev/DanishDev&Projects/AiCareerToolkitFE/aicareertoolkit-fe/src/routes/paths.ts)

Add:
```ts
retrievalTest: '/tools/retrieval-test',
```

---

#### [MODIFY] [AppRouter.tsx](file:///home/danish-ansari/Desktop/ProjectDev/DanishDev&Projects/AiCareerToolkitFE/aicareertoolkit-fe/src/routes/AppRouter.tsx)

Import and register the new private route:
```tsx
import { RetrievalTestPage } from '@/pages/retrieval-test/RetrievalTestPage'
// ...
<Route path={PATHS.retrievalTest} element={<RetrievalTestPage />} />
```

---

#### [MODIFY] [Sidebar.tsx](file:///home/danish-ansari/Desktop/ProjectDev/DanishDev&Projects/AiCareerToolkitFE/aicareertoolkit-fe/src/components/shared/Sidebar.tsx)

Add a new nav item with `FlaskConical` (lucide icon for "lab/testing") **immediately after the Memory Bank entry** in `NAV_ITEMS`:
```ts
{ label: 'Memory Bank',    path: PATHS.memoryBank,      icon: Brain },
{ label: 'Retrieval Test', path: PATHS.retrievalTest,   icon: FlaskConical },  // ← new, after Memory Bank
```

---

#### [NEW] `src/pages/retrieval-test/RetrievalTestPage.tsx`

The main page — the star of the show. Contains:

**Layout (3 sections, stacked vertically):**

1. **Header** — `PageHeader` with title "Vector Retrieval Lab" and subtitle about debugging the semantic search pipeline.

2. **Input Area (Query Panel)**
   - Large `<textarea>` with placeholder `"Describe what you're looking for, e.g. Looking for a dev who knows React Native and state management"`
   - **Top-K Slider** — `<input type="range" min={3} max={10} step={1} />` with a live label showing `"Top {k} results"`. Styled with emerald accent to match design system.
   - **"Test Retrieval" button** — triggers the API call, shows a spinner while loading
   - Status badge: shows `"Embedding query with gemini-embedding-001…"` while loading

3. **Results Panel**
   - Shows after results come back
   - Header: `"Found {n} semantic matches for: "{query}""`
   - Grid of **Result Cards** (one per chunk)

**Result Card anatomy:**
```
┌────────────────────────────────────────────────────────┐
│ [category badge]                    [89% Match] ← score │
│                                                          │
│ Title: "Software Engineer @ Acme Corp"                  │
│                                                          │
│ Content: full chunk text (truncated at ~300 chars with   │
│          a "Show more" toggle)                           │
│                                                          │
│ ── Metadata ──────────────────────────────────────────  │
│ ID: #42   Created: Aug 12, 2026                         │
└────────────────────────────────────────────────────────┘
```

**Similarity Score Color Coding:**
| Score | Color |
|-------|-------|
| ≥ 80% | Emerald green |
| 60–79% | Amber/yellow |
| < 60% | Slate/grey |

**Empty / error / zero-results states** all handled gracefully with contextual messages.

---

## Verification Plan

### Automated Tests
- None required — this is a debug/dev tool, not a production feature.

### Manual Verification (Step-by-Step)

1. **Start backend** (`bash start.sh`) — already running.
2. **Hit the endpoint directly** with `curl` or Swagger UI at `/docs`:
   ```bash
   curl -X POST http://localhost:8000/api/v1/memory/test-retrieval \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"query": "React Native developer", "top_k": 5}'
   ```
3. **Verify** the response contains `similarity_score` fields between 0–1.
4. **Navigate** to `http://localhost:5173/tools/retrieval-test` in the browser.
5. **Paste a query**, click "Test Retrieval", confirm result cards render with scores.
6. **Test edge cases**: empty DB, wrong query, network error.
