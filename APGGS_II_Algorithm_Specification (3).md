# APGGS-II: Algorithm Specification
### Adaptive Probe-Guided Genetic Search for the Traveling Salesman Problem

This document formalizes the implementation as a set of algorithm blocks and
numbered equations, in the style of a standard heuristic-optimization paper
(construction → memory-guided evolution → adaptive local search → escape
mechanism → selective exact-solver polish).

---

## 1. Problem Definition and Notation

Given a complete graph *G(V, E)* with *n = |V|* cities and a symmetric
distance matrix `dist[i][j]`, a **tour** *T* is a permutation of *V*. Its
cost is

```
L(T) = Σ_{i=0}^{n-1} dist( T[i], T[(i+1) mod n] )                     (1)
```

Two derived quantities are used throughout the search:

```
fitness(T) = 1 / max( L(T), 1e-12 )                                    (2)

gap%(T)    = ( L(T) − L* ) / L*  × 100                                 (3)
```

where *L\** is the best-known optimum for the instance (used only for
reporting/stopping, not for guiding the search itself).

Each city *i* is additionally given a **candidate list** `N[i]`, its *k*
nearest neighbours by distance (`k = 15` by default). Every local-search and
memory operator below only ever proposes reconnections drawn from these
lists — this is what keeps a single pass of any operator at *O(n·k)* instead
of *O(n²)*.

---

## 2. Algorithm 1 — Main Adaptive Generational Loop

**Input:** TSP instance *I*, initial population *P₀* (|P₀| = 70), candidate
lists *N*, configuration Θ
**Output:** best tour *T\**, best cost *L\**

```
1:  P := P0 ;  PMG := new PredictiveMemoryGraph() ;  PMG.update(P)
2:  Selector := new AdaptiveOperatorSelector()
3:  Stagnation := new StagnationDetector(window=15, ε=1e-4, floor=0.05)
4:  T*, L* := argmin/min cost in P ;  no_improve := 0
5:  if L* already matches known optimum then return (T*, L*)
6:  for generation g := 1 to 300 do
7:      Pnext := top 2 individuals of P unchanged                (elitism)
8:      segs  := PMG.elite_segments(top_k = 30)
9:      while |Pnext| < 70 do
10:         parent1 := TournamentSelect(P, size=4)
11:         parent2 := TournamentSelect(P, size=4)
12:         p_seg := 0.40 × max(0.25, PMG.trust)                       (4)
13:         child := SegmentCrossover(parent1, parent2, segs) 
                      with probability p_seg, else OX(parent1, parent2)
14:         if rand() < 0.20 then child := SwapMutation(child, frac=0.02)
15:         if rand() < 0.35 then child := TwoOpt(child, N, passes=1)
16:         Pnext := Pnext ∪ {child}
17:     P := Evaluate(Pnext) ;  PMG.update(P)
18:     op := Selector.select()                                        (5)
19:     apply op to the 14 cheapest individuals in P, keep only
             replacements that strictly reduce cost
20:     Selector.update(op, relative_gain)                             (6)
21:     div := PopulationDiversity(P, samples = 40)                    (7)
22:     stagnant := Stagnation.observe(min-cost(P), div)                (8)
23:     if not stagnant and min-cost(P) improved this generation then
24:         PMG.trust := min(1, PMG.trust + 0.05)                      (9)
25:     else if stagnant then
26:         PMG.trust := 0.15                                         (10)
27:         replace worst max(2, 70/6)=11 individuals in P with
                 TwoOpt( DoubleBridge(T*), N, passes=1 )
28:     if g mod 15 = 0 then
29:         for the 3 cheapest individuals in P:
30:             polished := SelectiveLKH(individual.tour, runs=3)
31:             keep polished only if strictly cheaper
32:     if min-cost(P) < L* then
33:         T*, L* := argmin/min cost in P ;  no_improve := 0
34:     else no_improve := no_improve + 1
35:     if L* has reached known optimum then break
36:     if no_improve ≥ 30 then break
37: return (T*, L*)
```

---

## 3. Algorithm 2 — Initial Population Construction

**Input:** instance *I*, candidate lists *N*
**Output:** population *P₀*, |P₀| = 70

```
1:  seed := GreedyEdgeConstruction(dist)                    // union-find edge join
2:  seed := TwoOpt(seed, N, passes=1)
3:  seed := TwoOpt(seed, N, passes=3)                        // no LKH at this stage
4:  P0 := { }
5:  for each start city s in V:
6:      candidates.append( NearestNeighborTour(dist, start=s) )
7:  P0 := P0 ∪ best 17 tours from candidates by L(T)                    (11)
8:  P0 := P0 ∪ { seed }
9:  for i := 1 to 10:
10:     t := GreedyEdgeConstruction(dist)
11:     with probability 0.75: apply one random swap to t              // diversify
12:     P0 := P0 ∪ { t }
13: while |P0| < 70:
14:     P0 := P0 ∪ { RandomPermutation(V) }
15: return P0
```

Population split: **17 nearest-neighbour + 11 greedy-edge (incl. the
optimized seed) + 42 random = 70.**

---

## 4. Algorithm 3 — Predictive Memory Graph (PMG) Update

The PMG is a decaying, trust-gated memory over four structures: **edge
memory**, **successor memory**, **segment memory**, and a curated
**prediction memory**, plus a scalar **trust ∈ [0, 1]**.

**Input:** current population *P*
**Output:** updated memory state

```
1:  for every stored key k in edge/successor/segment memory:
2:      value(k) := value(k) × 0.92                                    (12)
3:      if value(k) < 1e-5 then delete k                       // forgetting
4:  elites := top 20% of P by cost ;  best := min cost in elites
5:  for each individual e in elites:
6:      weight := best / max(e.cost, 1e-12)                            (13)
7:      for each edge (a,b) in e.tour:
8:          edge_memory[a,b]      += weight                            (14)
9:          successor_memory[a][b] += weight
10:         successor_memory[b][a] += 0.5 × weight            // asymmetric
11:     for L in {3, 4, 5}:
12:         for each length-L window w (wrapping) in e.tour:
13:             segment_memory[w] += weight                            (15)
14: rank all edges by edge_memory value, descending
15: count := max(1, floor(|edges| × 0.15 × trust))                     (16)
16: prediction_memory := top `count` edges
```

Two read-side quantities are used by later algorithms:

```
edge_quality(a, b) = trust × edge_memory[a, b]                         (17)

predicted_successors(city, k=5) = top-5 by successor_memory[city]
```

**Trust update is asymmetric — worth stating precisely:**

```
on improvement:  trust := min(1, trust + 0.05)                         (9)
on stagnation:    trust := clamp(0.15, 0, 1) = 0.15                    (10)
```

Trust rises **incrementally** on good generations but is **hard-reset to
0.15** on stagnation, not proportionally reduced — a deliberate "snap back to
cautious" behaviour rather than a gradual decay.

---

## 5. Algorithm 4 — Genetic Operators

```
TournamentSelect(P, size):
    return argmin cost of `size` individuals sampled uniformly from P

OX(parent1, parent2):
    pick random slice [i, j] of parent1 → copy into child
    fill remaining child positions with parent2's cities,
        in parent2's order, skipping cities already placed

SegmentCrossover(parent1, parent2, segs):
    usable := { s ∈ segs : 2 ≤ |s| < n, s has no repeated city,
                every city of s appears in parent1 }
    if usable = ∅: return OX(parent1, parent2)
    s := random choice from usable
    place s at parent1's position of s[0] if it fits without wrapping,
        else at a random valid offset
    fill remaining positions from parent2's order, as in OX
    return child

SwapMutation(tour, frac=0.02):
    perform max(1, ⌊n·frac⌋) random pairwise swaps
```

`SegmentCrossover` differs from `OX` only in **where the inherited block
comes from**: instead of an arbitrary contiguous slice of parent 1, it is a
sub-route that PMG has already seen perform well across recent elites
(Eq. 15–16).

---

## 6. Algorithm 5 — Adaptive Local-Search Operator Selection

Three candidate operators: `weak_edge_surgery`, `predictive_or_opt`,
`two_opt`. Each carries a scalar **credit**, initialised to 1.0.

**Selection probability** (credit-weighted with an exploration floor):

```
p_i = 0.10 + 0.70 × credit_i / Σ_j credit_j                            (18)
```

*(Note: Σ_i p_i = 1 by construction for any credit values, so the
renormalisation step performed in code is a no-op — worth knowing if asked
to derive it live.)*

**Credit update**, after applying the chosen operator to the 14 cheapest
individuals and observing `relative_gain` in population-best cost:

```
reward   = 1 + 20 × max(0, relative_gain)                              (19)
credit_i = 0.75 × credit_i + 0.25 × reward                              (6)
```

This is a **credit-weighted roulette wheel with an exponential-moving-average
reward**, not the textbook UCB1 rule (which adds an explicit
`√(2·ln t / n_i)` exploration bonus derived from visit counts). If a judge
asks for the UCB1 confidence-bound term specifically, this selector does not
compute one — it solves the same explore/exploit problem with a simpler
mechanism.

**`weak_edge_surgery`** — targets edges that are both poorly reinforced in
memory *and* long:

```
1: for each tour edge (a,b) at position i:
2:     key(i) := ( edge_quality(a,b), −dist(a,b) )                     (17)
3: sort positions ascending by key(i)           // weakest, then longest, first
4: weak := first max(3, n/10) positions
5: for each weak position i, city a = tour[i]:
6:     targets := predicted_successors(a, k=5) ∪ N[a]
7:     for each target t in targets:
8:         build trial tour by reversing the segment between i and
                pos(t) (only if that segment does not wrap)
9:         if trial is valid and L(trial) + ε < L(tour): return trial
10: return tour unchanged
```

**`predictive_or_opt`** — identical to standard Or-opt (segment relocation,
segment length ∈ {1,2,3}) except the candidate reconnection list is sorted
so that any candidate matching an edge in `prediction_memory` is tried
first:

```
removed_cost = dist(before, seg[0]) + dist(seg[-1], after)
               − dist(before, after)                                   (20)
forward_cost = dist(city, seg[0]) + dist(seg[-1], next) − dist(city,next)
reverse_cost = dist(city, seg[-1]) + dist(seg[0], next) − dist(city,next)
accept if  min(forward_cost, reverse_cost) + ε < removed_cost
```

**`two_opt`** — standard candidate-list-restricted 2-opt:

```
old = dist(a,b) + dist(c,d)
new = dist(a,c) + dist(b,d)                                            (21)
accept if  new + ε < old
```

---

## 7. Algorithm 6 — Diversity, Stagnation Detection, Double-Bridge Escape

**Population diversity** (edge-set dissimilarity, sampled):

```
diversity = (1/S) × Σ_{s=1}^{S} | E(Ta) Δ E(Tb) | / (2n)               (7)
```

for *S* = 40 randomly sampled pairs *(Ta, Tb)*, where *E(T)* is the set of
undirected edges in tour *T* and Δ is symmetric difference.

**Stagnation condition**, evaluated on a sliding window of the last 15
best-costs:

```
relative_improvement = (cost_oldest − cost_newest) / cost_oldest         (8)
stagnant = (relative_improvement < 1e-4)  AND  (diversity < 0.05)
```

Both conditions must hold simultaneously — slow-but-diverse search is not
flagged as stagnant.

**Double-bridge escape** (4-opt move, applied to the *global best* tour, not
to the individuals being replaced):

```
1: pick p1 < p2 < p3 uniformly from {1, ..., n−1}
2: A := T[0:p1] ;  B := T[p1:p2] ;  C := T[p2:p3] ;  D := T[p3:n]
3: return A + C + B + D
```

A double bridge cannot be undone by any single 2-opt move, which is why it
is the standard perturbation for escaping a 2-opt local optimum. Escaping
*around the current best* (rather than from a random individual) means the
search explores structural variants of the strongest known solution instead
of restarting blind.

---

## 8. Algorithm 7 — Selective LKH Polish

Applied to the 3 cheapest individuals every 15 generations:

```
1: try: result := elkai.solve(dist_matrix, runs=3)         // LKH-style solver
2:     if result is a valid tour and L(result) < L(current): return result
3: except: fall through
4: candidate := TwoOpt(current, N, passes=3)
5: candidate := OrOpt(candidate, N)
6: if L(candidate) < L(current): return candidate
7: return current unchanged
```

---

## 9. Stopping Conditions

Checked at the end of every generation, in order:

1. **Convergence:** global best cost has reached the known optimum
   (`gap% ≤ 0`, Eq. 3) → stop.
2. **Stall:** 30 consecutive generations with no new global best → stop.
3. Otherwise continue, up to a hard cap of 300 generations.

---

## 10. Parameter Table

| Parameter | Symbol | Value |
|---|---|---|
| Population size | — | 70 (17 NN / 11 Greedy / 42 Random) |
| Candidate list size | *k* | 15 |
| Tournament size | — | 4 |
| Mutation rate | — | 0.20 |
| Swap-mutation fraction | — | 0.02 |
| Segment-crossover base probability | — | 0.40 |
| Offspring local-search probability | — | 0.35 |
| Elitism count | — | 2 |
| PMG elite fraction | — | 0.20 |
| PMG decay | — | 0.92 |
| PMG prediction fraction | — | 0.15 |
| Adaptive-operator elite pool | — | 14 |
| Stagnation window | — | 15 generations |
| Stagnation epsilon | ε | 1e-4 |
| Diversity floor | — | 0.05 |
| LKH cadence | — | every 15 generations |
| LKH individuals / runs | — | 3 / 3 |
| No-improvement stop limit | — | 30 generations |
| Max generations | — | 300 |

---

## 11. Implementation Notes (for Q&A)

Small, honest details worth knowing cold if asked:

- **Operator selector** is a credit-weighted roulette wheel with an
  exploration floor and EMA reward (Eq. 18–19), not the literal UCB1
  upper-confidence-bound formula. Related idea, different mechanism.
- **`trust` is asymmetric**: incremented by +0.05 on improvement, but
  *hard-reset* to 0.15 on stagnation rather than reduced proportionally
  (Eq. 9–10).
- The probability renormalisation after Eq. 18 is mathematically redundant —
  the floor-plus-share formula already sums to 1 for any credit values.
- The first "greedy" individual in the initial population is labelled as
  including a Selective-LKH pass in its construction method string, though
  the seed-construction stage (Algorithm 2) does not actually call the LKH
  polish — LKH is intentionally deferred to run periodically inside the main
  loop instead (Algorithm 7). Cosmetic labelling, not a logic error.
