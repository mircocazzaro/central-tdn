import hashlib

RAW_TEMPLATES = [
    # Level 0
    {
      'level': 0,
      'template': '''ASK WHERE {
  ?pat a bto:Patient ;
       bto:hasDisease  {disease} .
}''',
      'params': ['disease'],
      'description': 'Is there any patient diagnosed with DISEASE?'
    },
    {
      'level': 0,
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
      'template': '''SELECT (COUNT(DISTINCT ?pat) AS ?nDISEASE) WHERE {
  ?pat a bto:Patient ;
       bto:hasDisease {disease} .
}''',
      'params': ['disease'],
      'description': 'How many patients are diagnosed with DISEASE?'
    },
    {
      'level': 1,
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
      'template': '''SELECT ?bracket (COUNT(DISTINCT ?pat) AS ?n) WHERE {
  ?pat a bto:Patient ;
       bto:hasDisease {disease} ;
       bto:undergo ?ev .
  ?ev  a bto:Onset ;
       bto:ageOnset ?ageOn .
  BIND(
    IF(?ageOn < {age1}, "{age1}",
      IF(?ageOn <= {age2}, "{age1}–{age2}", ">{age3}")
    ) AS ?bracket
  )
}
GROUP BY ?bracket''',
      'params': ['disease','age1','age2','age3'],
      'description': 'Count of DISEASE patients by age bracket'
    },
    # Level 4
    {
      'level': 4,
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
      'template': '''SELECT (MD5(STR(?pat)) AS ?anonID) ?ageOn ?b WHERE {
  ?pat a bto:Patient ;
       bto:hasDisease  {disease} ;
        bto:undergo ?ev .
  ?ev  a bto:Onset ;
       bto:ageOnset    ?ageOn ;
       bto:bulbarOnset ?b .
}''',
      'params': ['disease'],
      'description': 'Anonymized ALS‐onset profile (MD5 pat, age, onset age, bulbar)'
    },
    {
      'level': 5,
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
    """Return list of dicts with hash, level, params, template, and description."""
    out = []
    for e in RAW_TEMPLATES:
        h = hashlib.sha512(e['template'].encode()).hexdigest()
        out.append({
            'hash':        h,
            'level':       e['level'],
            'template':    e['template'],
            'params':      e['params'],
            'description': e['description'],
        })
    return out
