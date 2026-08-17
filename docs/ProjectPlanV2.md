## Upgraded Project Plan: AI Career Toolkit V2

We are keeping your **Modular Monolith** architecture. We will just add a new vertical slice for Memory. Here is the upgraded PRD.
### 1. Product Vision (Updated)

To build an automated toolkit that extracts job requirements, scores resumes, and **uses a semantic memory bank** of a user's entire career to generate perfectly tailored resumes on demand.
### 2. Modern Tech Stack (Updated for Phase 3.2)

- **Backend Framework:** FastAPI (Python).
- **AI Integration & Validation:** Pydantic + Instructor (Phase 3.1).
- **Database & Memory:** **PostgreSQL with `pgvector`**. We will use standard Postgres to store user data, and the `pgvector` extension turns it into a powerful vector database without needing a separate tool. This is perfect for a clean, world-class architecture.
- **AI Models:**
    - GPT-4o-mini (for fast structured extraction).
    - **OpenAI `text-embedding-3-small`** (for creating vectors).
    - Claude 3.5 Sonnet (for generating the final resume).
- **Deployment:** Docker & Docker Compose.



### The Complete AI Career Toolkit V2 Plan

#### Module 1: Job Description (JD) Extractor (The Target)

- **What it does:** Takes raw text from a job posting and converts it into strict, validated JSON (Title, Skills, Experience, Responsibilities).
    
- **AI Engineering Concept:** **Structured Outputs & Prompt Engineering.** You are using Pydantic schemas to force the LLM to return exactly the data types you need.
    
- **Status:** You have already built the core of this!
    

#### Module 2: Resume Ingestion Engine (The Onboarding)

- **What it does:** Extracts data from your existing PDF resume and converts it into a structured JSON format.
    
- **AI Engineering Concept:** **Data Chunking & Embedding.** The system will break your resume down into semantic chunks (e.g., separating Project A from Project B), call an embedding model (like `text-embedding-3-small`), and save both the text and the vector array into PostgreSQL.
    

#### Module 3: Career Memory Bank (The RAG Core)

- **What it does:** A database of your entire professional life. It stores your skills, projects, bug fixes, and experiences as vectors. You can manually add new achievements to this bank at any time without updating a PDF.
    
- **AI Engineering Concept:** **Vector Database (pgvector) & Semantic Search.** Instead of searching for exact keywords, the database understands the _meaning_ of your experience.
    

#### Module 4: The Gap Analyzer & ATS Scorer (The Validator)

- **What it does:** It acts like an ATS scanner. It takes the JSON from Module 1 (JD) and runs a semantic search against your Memory Bank (Module 3).
    
- **How it works:** It calculates a match percentage. If the JD requires "Docker" and your memory bank has vectors relating to "Containerization and Docker-Compose", it marks it as a match. It then returns a list of "Missing Skills" or "Experience Gaps".
    

#### Module 5: Context-Aware Resume & Outreach Generator (The Output)

- **What it does:** If the Gap Analyzer shows a good match, you click "Generate".
    
- **AI Engineering Concept:** **Retrieval-Augmented Generation (RAG).**
    
    1. The system takes the JD requirements.
        
    2. It retrieves the top 10 most relevant experiences from your Memory Bank.
        
    3. It feeds the JD and those 10 experiences to Claude 3.5 Sonnet.
        
    4. Claude generates a highly tailored PDF Resume, a custom Cover Letter, and a short LinkedIn connection message.
        

#### Module 6: Personal Job CRM (The Tracker)

- **What it does:** A simple Kanban board (Saved, Applied, Interviewing, Rejected) to track your applications.
    
- **Tech Concept:** Relational Database Design. Every job application links to the specific JD JSON and the exact tailored resume PDF you generated for it, so you never lose track.
    

#### Module 7: AI Mock Interviewer (The Practice)

- **What it does:** An interactive chat interface where an AI acts as the hiring manager.
    
- **AI Engineering Concept:** **Context-Window Management & System Prompts.** The system feeds the tailored resume and the JD into the LLM's context window. The LLM is instructed to ask technical and behavioral questions strictly based on the intersection of the JD requirements and your resume claims.
    

### Suggested Execution Path (How to build this)

To keep this manageable and ensure you are learning properly, you should build it in this order:

1. **Step 1: Database Setup.** Update your Docker Compose to use `pgvector`. Create the tables for the Career Memory Bank.
    
2. **Step 2: The Ingestion Pipeline.** Build a small script to test taking a text string, getting its vector from OpenAI, and saving it to your new database table.
    
3. **Step 3: The Search Pipeline.** Write the Python function to perform a similarity search (Cosine Similarity) in Postgres.
    
4. **Step 4: The Generation Pipeline.** Connect the search results to Claude/Llama to generate a custom resume block.