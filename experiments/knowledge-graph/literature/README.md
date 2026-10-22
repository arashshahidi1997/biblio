# Foundations: literature behind the knowledge-graph and wiki design

92 works that define the ideas the experiment and the pixecog wiki build on:
knowledge representation, knowledge graphs, claim and evidence models,
argumentation, Zettelkasten and hypertext, faceted classification, and the
philosophy of science that gives claims their levels and status.

Use the citekeys below in design docs, schema comments and wiki pages. When a
design choice rests on one of these works, cite it.

## Files

| File | What |
|------|------|
| `dois.txt` | 60 DOIs (verified 2026-10-22 against doi.org, Crossref, DataCite) |
| `manual.bib` | 32 hand-written entries: no DOI, DOI of a later edition, or broken registry metadata |
| `build_bib.py` | builds `foundations.bib` from both (CSL-JSON via doi.org; keys from `biblio.citekey`) |
| `foundations.bib` | generated, do not edit; linked into `bib/srcbib/` so `biblio bibtex merge` picks it up |

```bash
python experiments/knowledge-graph/literature/build_bib.py
biblio bibtex merge
```

Metadata comes from Crossref and DataCite on purpose. `biblio ingest dois`
takes OpenAlex records, which on this list returned the wrong work for two
arXiv DOIs, dropped book authors, and typed every entry as `@article`.

## Design questions and their sources

### What is a knowledge graph, and which data model?

- `hogan_2021_KnowledgeGraphs`: the reference survey. Directed labeled graphs
  vs property graphs, identity, context and qualifiers, quality, refinement.
- `ehrlinger_2016_TowardsDefinition`: what separates a knowledge graph from a
  knowledge base.
- `paulheim_2016_KnowledgeGraph`: completion and error detection. A model for
  the wiki's lint and refactor passes.
- `bizer_2009_LinkedData`, `bernerslee_2001_SemanticWeb`: resolvable
  identifiers and links to external IDs (DOI, ORCID, OpenAlex, ROR).
- `vrandecic_2014_Wikidata`: the statement model (claim, qualifiers,
  references, rank). A direct template for claim provenance.

### How do we write the schema itself?

- `noy_2001_OntologyDevelopment`: start from competency questions, separate
  classes from instances. `competency/questions.yml` follows this method.
- `gruber_1993_TranslationApproach`, `gruber_1995_TowardPrinciples`: ontology
  as an explicit specification; design criteria such as minimal ontological
  commitment, which argues for a small reference schema.
- `guarino_1998_FormalOntology`: top-level, domain, task and application
  ontologies. Our reference schema is an application ontology.
- `smith_2005_RelationsBiomedical`, `smith_2007_OboFoundry`: formally defined
  relations (`part_of`, `derives_from`) and orthogonal, versioned vocabularies.
- `brachman_1983_WhatIs`: keep subclass, instance-of and similarity links
  apart. A guard against overloaded tags.
- `davis_1993_WhatIs`, `minsky_1974_FrameworkRepresenting`,
  `quillian_1968_SemanticMemory`: what a representation commits to; frames with
  slots (typed pages with frontmatter); semantic networks.
- Background books: `sowa_2000_KnowledgeRepresentation`,
  `brachman_2004_KnowledgeRepresentation`, `arp_2015_BuildingOntologies`,
  `allemang_2020_SemanticWeb`, `studer_1998_KnowledgeEngineering`.

### Claims, evidence and provenance

- `groth_2010_AnatomyNanopublication`, `kuhn_2016_DecentralizedProvenance`:
  assertion, provenance and publication info kept apart; content-hashed,
  immutable claims that fit git and DataLad.
- `clark_2014_MicropublicationsSemantic`: claim, evidence, support and
  challenge, at levels from minimal to full.
- `ciccarese_2008_SwanBiomedical`: hypothesis, claim and research question as
  discourse elements, from the Alzheimer's research community.
- `brush_2016_SepioSemantic`: the evidence line between a claim and its data.
- `waard_2009_HypothesesEvidence`, `waard_2010_ProteinsFairytales`,
  `shotton_2009_SemanticPublishing`: papers as networks of hypotheses and
  evidence; claims hedged into facts over time.
- `lebo_2013_ProvO`, `wilkinson_2016_FairGuiding`: provenance vocabulary and
  FAIR identifiers.

### Epistemic status and levels (theory, hypothesis, claim)

- `latour_1979_LaboratoryLife`: statement types 1 to 5, from speculation to
  taken-for-granted fact. A scale for claim status.
- `latour_1987_ScienceAction`: claims harden or weaken as others cite them.
- `toulmin_1958_UsesArgument`: claim, data, warrant, backing, qualifier,
  rebuttal. The qualifier is the hook for status.
- `lakatos_1970_FalsificationMethodology`: hard core and protective belt.
  Grounds separate Theory and Hypothesis nodes and where anomalies attach.
- `kuhn_1962_StructureScientific`: paradigms and anomalies; why open problems
  deserve their own nodes.

### Typed relations and citations

- `peroni_2012_FabioCito`, `peroni_2018_SparOntologies`: CiTO citation types
  (supports, disputes, extends, usesMethodIn). Source of the
  `citation_intents` list in the reference schema.
- `buckinghamshum_2006_ModelingNaturalistic`, `buckinghamshum_2000_ScholontoOntology`,
  `uren_2006_SensemakingTools`: claim relations across papers and a user
  evaluation of a claim network.
- `greenberg_2009_HowCitation`: a claim-specific citation network showing
  how citation distortion creates unfounded authority. The case for typed
  citation edges.
- `nicholson_2021_SciteSmart`: supporting, contrasting and mentioning
  statements at scale.
- `teufel_2002_SummarizingScientific`: argumentative zoning; extracting
  claims by rhetorical role.
- `walton_2008_ArgumentationSchemes`: argument patterns with critical
  questions, usable as review prompts.

### Open questions and gaps

- `kunz_1970_IssuesElements`, `conklin_1988_GibisHypertext`: IBIS. Issues
  (questions) as first-class nodes with positions and arguments.
- `swales_1990_GenreAnalysis`: the CARS model; how introductions establish a
  niche. Where explicit gaps are found in a paper.
- `swanson_1986_UndiscoveredPublic`: literature-based discovery. Implicit gaps
  between disconnected literatures (CQ09).

### Atomic notes, links and the wiki

- `luhmann_1981_KommunikationMit` (English: `luhmann_1981_CommunicatingSlip`),
  `schmidt_2016_NiklasLuhmann`, `schmidt_2018_NiklasLuhmann`: how a long-lived
  slip box worked in practice: fixed IDs, branching, keyword register,
  cross-links.
- `ahrens_2017_HowTake`, `matuschak_nd_EvergreenNotes`,
  `appleton_2020_BriefHistory`, `milo_nd_LinkingYour`: atomic and evergreen
  notes, digital gardens, maps of content.
- `rayward_1994_VisionsXanadu`: Otlet's monographic principle, splitting
  documents into linkable facts.
- `bush_1945_AsWe`, `nelson_1965_ComplexInformation`,
  `engelbart_1962_AugmentingHuman`, `leuf_2001_WikiWay`: associative trails,
  hypertext, augmentation, and the wiki way.
- `procida_nd_Diataxis`: one documentation mode per page.
- `karpathy_2026_LlmWiki`: the LLM-maintained wiki pattern.
- History: `blair_2010_TooMuch`, `krajewski_2011_PaperMachines`.

### When to formalize

- `shipman_1999_FormalityConsidered`: forcing types at capture time costs
  users and produces bad structure. Argues for incremental formalization: an
  agent proposes types and links later, a person accepts them. Grounds the
  `candidate` status and the wiki's "grow, don't pre-build".
- `marshall_1995_SpatialHypertext`: structure that emerges before explicit
  links.
- `pirolli_2005_SensemakingProcess`, `chan_2024_StepsTowards`: the foraging
  and sensemaking loops; discourse graphs as a synthesis infrastructure.
- `novak_2008_TheoryUnderlying`: concept maps as propositions with linking
  phrases.

### Faceted tags and controlled vocabularies

- `ranganathan_1967_ProlegomenaLibrary`, `ranganathan_1933_ColonClassification`:
  facets (PMEST) and the colon notation that `facet:value` tags descend from.
- `svenonius_2000_IntellectualFoundation`: entities, attributes and controlled
  vocabularies.
- `hjorland_2013_FacetAnalysis`, `labarre_2010_FacetAnalysis`: what facet
  analysis does well and where it fails.
- `miles_2009_SkosReference`: SKOS, the standard format for a vocabulary with
  broader, narrower and alternative labels.

### People, citations and scholarly entities

- `priem_2022_OpenalexFully`, `nielsen_2017_ScholiaScientometrics`: the entity
  model behind a07 and profile pages generated from graph queries.
- `garfield_1955_CitationIndexes`, `price_1965_NetworksScientific`,
  `small_1973_CoCitation`: the citation network as an object of study;
  co-citation for clustering.
- `jaradeh_2019_OpenResearch`, `auer_2020_ImprovingAccess`: ORKG contributions
  and comparisons (a03).

### Neuroscience vocabularies

- `poldrack_2011_CognitiveAtlas`, `larson_2009_OntologiesNeuroscience`,
  `bug_2008_NifstdBirnlex`, `bandrowski_2015_ResourceIdentification`.

### LLMs and knowledge graphs

- `pan_2024_UnifyingLarge`, `edge_2024_LocalGlobal`, `ji_2022_SurveyKnowledge`,
  `collins_1969_RetrievalTime` (semantic-network retrieval, for contrast).

## Tensions the literature names

These bear directly on choices still open in the experiment and the wiki spec.

1. **Formal types vs low-friction capture.** Ontology engineering
   (`smith_2007_OboFoundry`, `arp_2015_BuildingOntologies`) asks for strict,
   well-defined types. `shipman_1999_FormalityConsidered` reports that users
   avoid or misuse them. Reconciling both: types stay strict in the schema,
   and assigning them is deferred and agent-assisted.
2. **Realist vs pragmatic ontology.** BFO (`arp_2015_BuildingOntologies`)
   models what exists; Gruber models what a community agrees to talk about.
   A project wiki is the second kind.
3. **Facets as logic vs facets as convenience.** `hjorland_2013_FacetAnalysis`
   argues facet analysis cannot be purely a priori. Expect the vocabulary to
   change with use, and record the changes.
4. **Claims as facts vs claims as statements.** `latour_1979_LaboratoryLife`
   treats facthood as something a statement acquires. Store claims with a
   status that can change, and keep superseded versions (the wiki's P9).
5. **Atomic notes vs papers as units.** Luhmann's cards and the wiki's pages
   are idea-sized; bibliographic tools are paper-sized. Claim-level IDs are
   where the two meet.

## Start here (12)

1. `hogan_2021_KnowledgeGraphs`: data model, identity, quality.
2. `groth_2010_AnatomyNanopublication`: the template for an atomic claim with provenance.
3. `clark_2014_MicropublicationsSemantic`: claims, evidence, support, challenge.
4. `chan_2024_StepsTowards`: discourse graphs as atomic, linked notes.
5. `peroni_2012_FabioCito`: a standard vocabulary for typed citations.
6. `latour_1979_LaboratoryLife`: a principled scale of epistemic status.
7. `lakatos_1970_FalsificationMethodology`: theory vs auxiliary hypotheses.
8. `schmidt_2018_NiklasLuhmann`: how a real slip box worked (short, open access).
9. `shipman_1999_FormalityConsidered`: why types should be added late.
10. `hjorland_2013_FacetAnalysis`: faceted tags and their limits.
11. `noy_2001_OntologyDevelopment`: a practical method for writing the schema.
12. `edge_2024_LocalGlobal`: an LLM building and summarizing a graph over a corpus.

## Not yet verified

- `kunz_1970_IssuesElements`: the working-paper number (131) is from standard
  citations; only the 2013 reprint DOI was checked.
- `quillian_1968_SemanticMemory`: page range omitted.
- `ranganathan_1933_ColonClassification`: no stable scan located.
