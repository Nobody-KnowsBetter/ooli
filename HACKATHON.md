# HACKATHON.md

## Team name
Binary Bandits

## Team members
- Nitanshu Goyal
- Mausam Kumar Dwivedi
- Himank Kaushik
- Krish Garg

## Problem statement
Problem 5: Automated Documentation Drift Detection

## Models we use and why
- Qwen 2.5 Coder 3B: Decides whether a documentation sentence that has a changed setting's old value but doesn't name the setting (for example "Requests give up after 30 seconds") is really about that setting or only a coincidence. Exact matches are decided by rules, so the model only answers this one question. Small enough to run on a laptop: about 2 GB of memory, locally via Ollama.
