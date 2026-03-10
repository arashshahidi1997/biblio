High impact, focused scope
1. Paper recommendations panel
The most ResearchRabbit-like feature still missing. Using the graph candidates you already have, rank external papers by how many of your local papers cite or are cited by them (co-citation frequency). A "Discover" tab or panel that surfaces the top 20 papers not yet in your library, ranked by overlap with your corpus. This is exactly what LocalCitationNetwork does and it's largely a backend scoring pass over graph_candidates.json.

2. Semantic search over full docling text
The RAG tab exists but the search UI in SearchTab is likely using a separate tool. Integrating semantic search results directly into the network (highlight matching nodes) or the library (rank by relevance) would make it much more useful. Right now search and graph feel disconnected.

3. Year legend + color scale strip
The year-based node coloring was just added but there's no legend. A small gradient strip showing old → recent below the graph would make it interpretable. 5-minute CSS addition.

Network graph depth
4. 2-hop expansion (incremental)
Right now "Expand Selected" fetches neighbors of one paper. A "go deeper" button that expands neighbors-of-neighbors for the selected node would make the network feel truly exploratory like ResearchRabbit. This needs a depth param in the backend.

5. Edge weight / co-citation opacity
Edges between two external neighbors that are both cited by multiple local papers could be drawn thicker. The Salton similarity score from inciteful is the right metric. Pure frontend math over the existing candidates data.

6. Community clustering colors
Group nodes by detected cluster (e.g. Louvain over the adjacency matrix) and color local papers by their cluster. The cytoscape-community or a simple JS implementation would work. Gives a topical map feel.

Workflow / UX
7. Paper notes panel
The extras.notes field already exists in the model. A simple text editor panel in the Paper tab (a textarea that auto-saves to a .md file via a new API endpoint) would make biblio a proper reading tool, not just a viewer.

8. Docling subtab reset on paper change
Currently if you're on the "Full Docling" subtab and switch papers via the tab strip, it stays on Full Docling. The subtab should reset to "PDF" when activePaperKey changes (just add a useEffect on activePaper.citekey).

9. Library column sort
The library table has no sort controls. Sortable columns (year, status, citekey, citation count from openalex) would be very useful for a large library.

Easiest wins
10. Docling run all — no "run Docling on all papers" button exists. The pipeline has GROBID (all) but Docling requires per-paper. Adding { all: true } support to the docling-run backend endpoint would complete the pipeline.

11. Clear action status — the action status bar stays visible until the next action. A dismiss × button or auto-fade after 5 seconds would clean up the UI.

My recommendation for next session: Start with (1) the recommendations panel — it's the highest-value feature for a bibliography research tool and requires only a new backend scoring function + a simple frontend panel. Then (8) the docling subtab reset since it's a 2-line fix, and (11) the status bar dismiss.