import os
import httpx
import asyncio
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

async def fetch_repo_files(owner: str, repo: str, branch: str = "main"):
    # First get the tree recursively
    url = "https://api.github.com/repos/{}/{}/git/trees/{}?recursive=1".format(owner, repo, branch)
    
    async with httpx.AsyncClient() as client:
        # User agent is required by GitHub API
        headers = {"User-Agent": "GitHub-Connector-POC"}
        response = await client.get(url, headers=headers)
        
        if response.status_code != 200:
            print("Failed to fetch repo: %s" % response.status_code)
            return []
            
        tree = response.json().get("tree", [])
        
        # Filter for python, js/ts files, and markdown
        valid_extensions = (".py", ".js", ".ts", ".tsx", ".md", ".json")
        files = [
            item for item in tree 
            if item["type"] == "blob" and item["path"].endswith(valid_extensions)
            and not item["path"].startswith("node_modules")
            and not item["path"].startswith(".venv")
        ]
        
        documents = []
        # Limit to 5 files for the POC to avoid excessive API calls
        limit = 5
        print("Found %d target files. Fetching first %d for POC..." % (len(files), limit))
        
        for f in files[:limit]:
            # Fetch raw content
            raw_url = "https://raw.githubusercontent.com/{}/{}/{}/{}".format(owner, repo, branch, f['path'])
            res = await client.get(raw_url)
            if res.status_code == 200:
                print("  + Fetched: %s" % f['path'])
                documents.append(
                    Document(
                        page_content=res.text, 
                        metadata={"source": f['path'], "repo": "{}/{}".format(owner, repo)}
                    )
                )
            else:
                print("  - Failed to fetch: %s" % f['path'])
                
    return documents

async def main():
    print("--- GitHub Connector POC ---")
    owner = "KurianJose7586"
    repo = "twinlyAI-Backend-v2.0"
    
    print("\n[1] Fetching target repository %s/%s..." % (owner, repo))
    docs = await fetch_repo_files(owner, repo)
    if not docs:
        print("No documents fetched. Exiting.")
        return
        
    print("\n[2] Chunking documents...")
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    splits = splitter.split_documents(docs)
    print("Split %d documents into %d chunks." % (len(docs), len(splits)))
    
    print("\n[3] Initializing Embeddings & Qdrant In-Memory Vector Store...")
    # Using a small fast local embedding model
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    
    qdrant = QdrantVectorStore.from_documents(
        splits,
        embeddings,
        location=":memory:", # In-memory Qdrant instance
        collection_name="github_poc",
    )
    print("Finished indexing.")
    
    print("\n[4] Querying the Vector Database...")
    query = "What endpoints does the application have?"
    print("Query: '%s'" % query)
    
    results = qdrant.similarity_search(query, k=2)
    
    print("\n--- Retrieval Results ---")
    for i, r in enumerate(results, 1):
        print("\nResult %d (Source: %s)" % (i, r.metadata['source']))
        print("-" * 40)
        # Print first 250 chars of the chunk
        snippet = r.page_content.strip()
        if len(snippet) > 250:
            snippet = snippet[:250] + "..."
        print(snippet)

if __name__ == "__main__":
    asyncio.run(main())
