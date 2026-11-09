Through cp-005 (38 moves), the player has won level 1 and begun level 2.
It calls the player a cursor; IDs 5/6/7 denote the cursor over 2/4/1 respectively.
It now calls 3 (level 1) and 8 (level 2) boxes and 0 the target.
It uses artificial heights 1->2, 4->3, 2->4 and |dh|<=1: correct ordinary colour walking and grey bridging.
The target is assigned a separate height 1, an untested extrapolation beyond the ordinary colour rules.
It understands one-cell pushing, corner deadlocks, and refusal of off-grid pushes; the classical Sokoban collision comparison is not clearly adopted for this variant.
solver2.py also explicitly preserves the box position on non-push walks (notebook M2 correct). It wrongly allows pushing from any floor and wrongly assumes box trails permanently become 1.
It believes a box can enter any floor and that placing the single box on its target wins; multiple-box quantification is not yet stated.
Old notes.md and solver.py still describe sliding-number sorting, but newer level2.md/solver2.py supersede that account.
ACTION7 is wrongly called random movement; M1 is partial because the four directions are known but action-button redundancy is unstated.
