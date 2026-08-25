# PuzzleScript-World Conference Paper

This directory is an Overleaf-ready research-paper draft in the same
ACM-style two-column format used by the recent joint student paper from
Noga Peleg-Pelc, Gal A. Kaminka, and Yoav Goldberg.

## Upload to Overleaf

Upload `main.tex` and `proposalbib.bib`, or upload the generated
`puzzlescript-world-overleaf.zip`.

The project uses the standard Overleaf `acmart` class with the `sigconf` and
`nonacm` options. This preserves the paper layout without adding false
conference, copyright, DOI, or publication metadata.

## Format references

The joint Kaminka--Goldberg paper is the primary layout reference. Four other
recent student-coauthored papers were checked to confirm the two-column
conference-paper convention:

1. Noga Peleg-Pelc, Gal A. Kaminka, and Yoav Goldberg,
   [A Language for Describing Agentic LLM Contexts](https://u.cs.biu.ac.il/~kaminkg/Publications/papers/cais26.pdf)
   (CAIS 2026).
2. Erel Shtossel and Gal A. Kaminka,
   [Modular Reinforcement Learning For Cooperative Swarms](https://u.cs.biu.ac.il/~kaminkg/Publications/papers/arms26.pdf)
   (AAMAS ARMS 2026).
3. Yifat Yankovich and Gal A. Kaminka,
   [A Model-Based Approach for Recognizing Unknown Goal Combinations](https://u.cs.biu.ac.il/~kaminkg/Publications/papers/yifat26ws.pdf)
   (AAAI ToM4AI 2026).
4. Hail Hochman, Natalie Shapira, and Yoav Goldberg,
   [Factual Retrieval in LLMs Is a Redundant, Distributed and Non-Contiguous Process](https://aclanthology.org/2026.acl-long.2168/)
   (ACL 2026).
5. Or Shachar, Uri Katz, Yoav Goldberg, and Oren Glickman,
   [NER Retriever: Zero-Shot Named Entity Retrieval with Type-Aware Embeddings](https://aclanthology.org/2025.findings-emnlp.597/)
   (Findings of EMNLP 2025).

## Local compilation

```powershell
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

The draft distinguishes:

- implemented benchmark functionality and confirmed repository evidence;
- proposed whole-game and warm/cold transfer protocols;
- experiments and measurements that have not yet been run.

Only Adam Celermajer is listed as an author. A comment in `main.tex` marks where
supervisors or coauthors can be added once the author list is finalized.
