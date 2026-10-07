import hashlib

RAW_TEMPLATES = [
    # Level 0
    {
      'level': 0,
      'key': 'q00_L0',
      'template': '''ASK WHERE {
  ?pat a bto:Patient ;
       bto:hasDisease  {disease} .
}''',
      'params': ['disease'],
      'description': 'Is there any patient diagnosed with DISEASE?'
    },
    {
      'level': 0,
      'key': 'q01_L0',
      'template': '''ASK WHERE {
  ?pat a bto:Patient ;
       bto:hasDisease {disease} ;
       bto:undergo ?eO.
  ?eO  a bto:Onset ;
       bto:ageOnset ?aO .
  FILTER(?aO < {age})
}''',
      'params': ['disease','age'],
      'description': 'Is there any DISEASE patient under AGE years old?'
    },
    # Level 1
    {
      'level': 1,
      'key': 'q02_L1',
      'template': '''SELECT (COUNT(DISTINCT ?pat) AS ?nDISEASE) WHERE {
  ?pat a bto:Patient ;
       bto:hasDisease {disease} .
}''',
      'params': ['disease'],
      'description': 'How many patients are diagnosed with DISEASE?'
    },
    {
      'level': 1,
      'key': 'q03_L1',
      'template': '''SELECT (COUNT(DISTINCT ?pat) AS ?nSex) WHERE {
  ?pat a bto:Patient ;
       bto:hasDisease {disease} ;
       bto:sex "{sex}" .
}''',
      'params': ['disease','sex'],
      'description': 'How many patients have DISEASE filtered by SEX?'
    },
    # Level 2
    {
      'level': 2,
      'key': 'q04_L2',
      'template': '''SELECT (AVG(?aO) AS ?avgAge) WHERE {
  ?pat a bto:Patient ;
       bto:hasDisease {disease} ;
       bto:undergo ?eO.
  ?eO  a bto:Onset ;
       bto:ageOnset ?aO .
}''',
      'params': ['disease'],
      'description': 'What is the average age at onset of DISEASE patients?'
    },
    {
      'level': 2,
      'key': 'q05_L2',
      'template': '''SELECT (AVG(xsd:integer(?diff)) AS ?medianSurvivalDays) WHERE {
  ?pat a bto:Patient ;
       bto:hasDisease {disease} ;
       bto:deathDate ?d .
  ?ev  a bto:Onset ;
       bto:eventStart ?s ;
       bto:registeredFor ?pat .
  FILTER ( bto:eventStart >= "{starting_date}"^^xsd:date )
  BIND( xsd:integer(?d) - xsd:integer(?s) AS ?diff )
}''',
      'params': ['disease','starting_date'],
      'description': 'Median survival time (days) from onset to death, after STARTING_DATE'
    },
    # Level 3
    {
      'level': 3,
      'key': 'q06_L3',
      'template': '''SELECT ?site (AVG(?ageOn) AS ?avgOnsetAge) 
WHERE {
  ?pat a bto:Patient ;
       bto:hasDisease NCIT:C34373 ;
       bto:undergo ?ev .
  ?ev  a bto:Onset ;
       bto:ageOnset ?ageOn ;
       bto:bulbarOnset ?b .
  BIND(IF(?b = true,"Bulbar","Spinal") AS ?site)
}
GROUP BY ?site''',
      'params': [],
      'description': 'Average age at onset grouped by bulbar vs spinal (ALS‐specific)'
    },
    { 
      'level': 3,
      'key': 'q07_L3',
      'analytics_key': 'ageDist',
      'template': '''SELECT ?bracket ?n WHERE {
SELECT ?bracket (AVG(?ageOn) AS ?avgAgeOn) (COUNT(DISTINCT ?pat) AS ?n) WHERE {
  ?pat a bto:Patient ;
       bto:hasDisease {disease} ;
       bto:undergo ?ev .
  ?ev  a bto:Onset ;
       bto:ageOnset ?ageOn .
  BIND(
    IF(?ageOn < {age1}, "<{age1}",
      IF(?ageOn <= {age2}, "{age1}–{age2}", IF(?ageOn <= {age3}, "{age2}-{age3}", ">{age3}")
    ) ) AS ?bracket
  )
}
GROUP BY ?bracket
ORDER BY ?avgAgeOn
}''',
      'params': ['disease','age1','age2','age3'],
      'description': 'Count of DISEASE patients by age bracket'
    },
    {
        'level': 3,
        'key': 'q08_L3',
        'template': '''SELECT ?question ?avgq ?grad WHERE {
  {
    SELECT ?question (AVG(?q) AS ?avgq) 
    WHERE {
      ?pat a bto:Patient ;
           bto:hasDisease NCIT:C34373 ;
           bto:undergo ?ev .
      ?ev  bto:consists ?alsfrs .
      ?alsfrs a bto:ALSFRS ;
              ?quest ?q .

      # <-- user-provided question URI goes here
      FILTER (?quest = {question})

      BIND(IF (
          ?quest = <https://w3id.org/brainteaser/ontology/schema/alsfrs1>, "I have been less alert", IF (
          ?quest = <https://w3id.org/brainteaser/ontology/schema/alsfrs2>, "I have had difficulty paying attention for long periods of time", IF (
          ?quest = <https://w3id.org/brainteaser/ontology/schema/alsfrs3>, "I have been unable to think clearly", IF (
          ?quest = <https://w3id.org/brainteaser/ontology/schema/alsfrs4>, "I have been clumsy and uncoordinated", IF (
          ?quest = <https://w3id.org/brainteaser/ontology/schema/alsfrs5>, "I have been forgetful", IF (
          ?quest = <https://w3id.org/brainteaser/ontology/schema/alsfrs6>, "I have had to pace myself in my physical activities", IF (
          ?quest = <https://w3id.org/brainteaser/ontology/schema/alsfrs7>, "I have been less motivated to do anything that requires physical effort", IF (
          ?quest = <https://w3id.org/brainteaser/ontology/schema/alsfrs8>, "I have been less motivated to participate in social activities", IF (
          ?quest = <https://w3id.org/brainteaser/ontology/schema/alsfrs9>, "I have been limited in my ability to do things away from home", IF (
          ?quest = <https://w3id.org/brainteaser/ontology/schema/alsfrs10>, "I have trouble maintaining physical effort for long periods", IF (
          ?quest = <https://w3id.org/brainteaser/ontology/schema/alsfrs11>, "I have had difficulty making decisions", IF (
          ?quest = <https://w3id.org/brainteaser/ontology/schema/alsfrs12>, "I have been less motivated to do anything that requires thinking", "" ) ) ) ) ) ) ) ) ) ) )) 
        
        AS ?question )
    }
    GROUP BY ?question
  }
  BIND(
    IF(?avgq < 0.5, "Never",
    IF(?avgq < 1.5, "Rarely",
    IF(?avgq < 2.5, "Sometimes",
    IF(?avgq < 3.5, "Often",
       "Almost Always"))))
    AS ?grad
  )
}''',
        'params': ['question'],
        'description': 'Average ALSFRS score for a selected question (with human-readable text and grading)',
    },
    # Level 4
    {
      'level': 4,
      'key': 'q09_L4',
      'template': '''SELECT ?ageOn ?sex WHERE {
  ?pat a bto:Patient ;
       bto:hasDisease {disease} ;
       bto:sex ?sex ;
       bto:undergo ?ev .
  ?ev  a bto:Onset ;
       bto:ageOnset ?ageOn .
}''',
      'params': ['disease'],
      'description': 'List ages & sexes of DISEASE patients (anonymized)'
    },
    {
      'level': 4,
      'key': 'q10_L4',
      'template': '''SELECT ?onsetTypes (COUNT(DISTINCT ?pat) AS ?n) WHERE {
  ?pat a bto:Patient ;
       bto:hasDisease {disease} ;
       bto:undergo ?ev .
  ?ev  a bto:Onset ;
       bto:eventStart     ?tDate ;
       bto:bulbarOnset  ?bOns ;
       bto:axialOnset  ?aOns ;
       bto:generalizedOnset  ?gOns ;
       bto:limbsOnset  ?lOns .
  BIND(
  	CONCAT(
    	IF(?aOns = true, "Axial", ""),
		IF(?bOns = true, "Bulbar", ""),
        IF(?gOns = true, "General", ""),
        IF(?lOns = true, "Limbs", "")
    ) AS ?onsetTypes
   )
}
GROUP BY ?onsetTypes''',
      'params': ['disease'],
      'description': 'Count of DISEASE patients by onset‐type combinations (Axial, Bulbar, General, Limbs)'
    },
    # Level 5
    {
      'level': 5,
      'key': 'q11_L5',
      'template': '''SELECT (MD5(STR(?pat)) AS ?anonID) ?ageOn ?b WHERE {
  ?pat a bto:Patient ;
       bto:hasDisease  {disease} ;
        bto:undergo ?ev .
  ?ev  a bto:Onset ;
       bto:ageOnset    ?ageOn ;
       bto:bulbarOnset ?b .
}''',
      'params': ['disease'],
      'description': 'Anonymized ALS‐onset profile (MD5 pat, age, onset age, bulbar)',
      'analytics_key': 'klDiv'
    },
    {
      'level': 5,
      'key': 'q12_L5',
      'template': '''SELECT (MD5(STR(?pat)) AS ?anonID)
       ?tDate ?onsetTypes WHERE {
  ?pat a bto:Patient ;
       bto:hasDisease    {disease} ;
       bto:undergo       ?ev .
  ?ev  a bto:Onset ;
       bto:eventStart     ?tDate ;
       bto:bulbarOnset  ?bOns ;
       bto:axialOnset  ?aOns ;
       bto:generalizedOnset  ?gOns ;
       bto:limbsOnset  ?lOns .
  BIND(
  	CONCAT(
    	IF(?aOns = true, "Axial", ""),
		IF(?bOns = true, "Bulbar", ""),
        IF(?gOns = true, "General", ""),
        IF(?lOns = true, "Limbs", "")
    ) AS ?onsetTypes
   )
}
ORDER BY ?anonID ?tDate''',
      'params': ['disease'],
      'description': 'Anonymized onset profile: MD5 hash of patient URI, age at onset, and bulbar‐onset flag for DISEASE patients'
    },
    # Level 6
    {
      'level': 6,
      'key': 'q13_L6',
      'template': '''SELECT * WHERE {
  ?pat a bto:Patient ;
       bto:hasDisease  {disease} ;
       ?p ?o .
}''',
      'params': ['disease'],
      'description': 'All data for DISEASE patients (including IDs)'
    },
    {
      'level': 6,
      'key': 'q14_L6',
      'template': '''SELECT ?pat ?name ?aOns ?sex ?ev ?evType ?evStart  WHERE {
  ?pat a bto:Patient ;
       bto:sex           ?sex ;
       bto:undergo      ?ev ;
       bto:hasDisease    {disease} .
  ?ev  a ?evType ;
       bto:ageOnset ?aOns ;
       bto:eventStart    ?evStart .
}''',
      'params': ['disease'],
      'description': 'Complete patient profiles for DISEASE'
    },
]

def catalog():
    out = []
    for e in RAW_TEMPLATES:
        h = hashlib.sha512(e['template'].encode()).hexdigest()
        entry = {
            'key':         e['key'],
            'hash':        h,
            'level':       e['level'],
            'template':    e['template'],
            'params':      e['params'],
            'description': e['description'],
        }
        if 'analytics_key' in e:
            entry['analytics_key'] = e['analytics_key']
        out.append(entry)
    return out


# Keys are the stable template ids shared with the endpoints' catalog
# (tdn-endpoint/myapp/catalog.py); never reuse or renumber them.
_KEYS = [e['key'] for e in RAW_TEMPLATES]
assert len(set(_KEYS)) == len(_KEYS), "duplicate template key in RAW_TEMPLATES"


def get_entry(key):
    """Catalog entry for ``key``, or None."""
    return next((e for e in catalog() if e['key'] == key), None)


# Parameter -> grammar name on the endpoints (PARAM_TYPES in
# tdn-endpoint/myapp/catalog.py). Templates with a parameter not listed here
# cannot be validated by the endpoints and are left out of the published
# catalog.
def wire_type(param):
    if param == 'disease':
        return 'disease'
    if param == 'question':
        return 'alsfrs_question'
    if param == 'sex':
        return 'sex'
    if param == 'age' or (param.startswith('age') and param[3:].isdigit()):
        return 'age'
    return None


def federated_templates():
    """``(published, skipped)``: entries for the endpoints, and (key, reason) left out."""
    published, skipped = [], []
    for e in RAW_TEMPLATES:
        types = {p: wire_type(p) for p in e['params']}
        missing = sorted(p for p, t in types.items() if t is None)
        if missing:
            skipped.append((e['key'], f"no endpoint grammar for {', '.join(missing)}"))
            continue
        published.append({
            'key': e['key'], 'level': e['level'], 'description': e['description'],
            'params': types, 'sha512': hashlib.sha512(e['template'].encode()).hexdigest(),
            'sparql': e['template'],
        })
    return published, skipped
