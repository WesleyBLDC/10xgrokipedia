#!/bin/bash
# Script to set up and generate the article graph

cd "$(dirname "$0")"

echo "Step 1: Backfilling UUIDs for articles..."
python3 backfill_uuids.py

echo ""
echo "Step 2: Generating article graph..."
python3 generate_article_graph.py

echo ""
echo "Graph setup complete! The graph data is now available at: article_graph.json"

