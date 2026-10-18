"""Curated MedlinePlus health-topic title shortlist for LifeLine's 100-topic offline demo.
These entries are a search catalog until refresh_medlineplus.py fills them with
actual NLM public-domain health-topic summaries. No clinical content is invented.
"""
SEED_GROUPS = {
    'Emergency and first aid': [
        'First Aid','Bleeding','Burns','Choking','CPR','Anaphylaxis','Poisoning',
        'Heart Attack','Stroke','Seizures','Shock','Heat Illness','Hypothermia',
        'Frostbite','Dehydration','Animal Bites','Insect Bites and Stings',
        'Snake Bites','Spider Bites','Concussion'
    ],
    'Injuries': [
        'Wounds and Injuries','Fractures','Sprains and Strains','Dislocations',
        'Back Injuries','Eye Injuries','Bruises','Blisters','Head Injuries',
        'Spinal Cord Injuries','Sports Injuries','Nosebleeds','Dental Injuries'
    ],
    'Breathing and lungs': [
        'Asthma','Acute Bronchitis','Chronic Bronchitis','Pneumonia',
        'Respiratory Syncytial Virus Infections','Flu','COVID-19',
        'Breathing Problems','COPD','Sleep Apnea'
    ],
    'Infections': [
        'Foodborne Illness','Salmonella Infections','Norovirus Infections',
        'Lyme Disease','Rabies','Tetanus','Meningitis','Sepsis','Tuberculosis',
        'Malaria','Dengue','Strep Throat','Ear Infections','Hepatitis A','HIV'
    ],
    'Stomach and digestion': [
        'Abdominal Pain','Appendicitis','Diarrhea','Nausea and Vomiting',
        'Constipation','Food Allergy','Gastroenteritis','Gastrointestinal Bleeding',
        'Pancreatitis','Peptic Ulcer','Gallstones','GERD'
    ],
    'Heart and circulation': [
        'Angina','Arrhythmia','Atrial Fibrillation','Blood Clots',
        'High Blood Pressure','Low Blood Pressure','Heart Failure',
        'Pulmonary Embolism','Coronary Artery Disease'
    ],
    'Diabetes and hormones': [
        'Diabetes','Type 1 Diabetes','Type 2 Diabetes','Hypoglycemia',
        'Hyperglycemia','Thyroid Diseases','Hypothyroidism','Hyperthyroidism',
        'Adrenal Gland Disorders'
    ],
    'Brain and nerves': [
        'Headache','Migraine','Dizziness and Vertigo','Fainting','Epilepsy',
        "Bell's Palsy",'Multiple Sclerosis',"Parkinson's Disease",'Neuropathy',
        "Alzheimer's Disease"
    ],
    'Skin and exposure': [
        'Eczema','Skin Infections','Cellulitis','Acne','Rashes','Hives',
        "Athlete's Foot",'Sunburn'
    ],
    'Other common issues': [
        'Urinary Tract Infections','Kidney Stones','Pregnancy Complications',
        'Ectopic Pregnancy','Anxiety','Panic Disorder','Depression'
    ]
}

# Candidate substitutions when topics were retired or renamed by MedlinePlus.
# Only exact/see-reference matches will be imported. These can fill any gaps.
EXTRA_CANDIDATES = [
    ('Emergency and first aid','Emergency Medical Services'),
    ('Emergency and first aid','Sudden Cardiac Arrest'),
    ('Emergency and first aid','Electrical Injuries'),
    ('Emergency and first aid','Carbon Monoxide Poisoning'),
    ('Emergency and first aid','Disaster Preparation and Recovery'),
    ('Injuries','Falls'),('Injuries','Hand Injuries and Disorders'),
    ('Injuries','Knee Injuries and Disorders'),('Injuries','Ankle Injuries and Disorders'),
    ('Breathing and lungs','Respiratory Failure'),('Breathing and lungs','Lung Diseases'),
    ('Breathing and lungs','Cough'),('Breathing and lungs','Sore Throat'),
    ('Infections','Viral Infections'),('Infections','Bacterial Infections'),
    ('Infections','Infection Control'),('Infections','Tick Bites'),
    ('Stomach and digestion','Heartburn'),('Stomach and digestion','Indigestion'),
    ('Stomach and digestion','Liver Diseases'),
    ('Heart and circulation','Atherosclerosis'),('Heart and circulation','Heart Diseases'),
    ('Diabetes and hormones','Blood Glucose'),('Diabetes and hormones','Endocrine Diseases'),
    ('Brain and nerves','Memory'),('Brain and nerves','Tremor'),
    ('Skin and exposure','Psoriasis'),('Skin and exposure','Rosacea'),
    ('Skin and exposure','Warts'),('Other common issues','Allergy'),
    ('Other common issues','Pregnancy'),('Other common issues','Fever'),
]

# Common layperson ways of describing topics, useful for FTS. These are search
# synonyms, not extra clinical claims.
ALIASES = {
 'Heat Illness':'heat stroke heatstroke heat exhaustion overheated extremely hot heat cramps',
 'Heart Attack':'chest pain myocardial infarction',
 'Stroke':'face drooping slurred speech one arm weakness',
 'Anaphylaxis':'severe allergic reaction allergic shock throat swelling',
 'Poisoning':'poison poison control swallowed chemicals overdose',
 'Hypothermia':'too cold freezing body cold exposure',
 'Frostbite':'frozen fingers frozen toes cold injury',
 'Bleeding':'blood cut deep wound bleeding heavily',
 'Wounds and Injuries':'cuts scrapes grazes lacerations',
 'Dehydration':'no water thirsty lightheaded dry mouth',
 'CPR':'cardiopulmonary resuscitation not breathing cardiac arrest',
 'Choking':'cant breathe food stuck throat blocked airway',
 'Seizures':'fit convulsions shaking seizure',
 'Concussion':'head hit fall hit head mild traumatic brain injury',
 'Sprains and Strains':'twisted ankle pulled muscle',
 'Snake Bites':'snakebite bitten by snake',
 'Spider Bites':'spider bite',
 'Insect Bites and Stings':'bee sting wasp sting insect bite',
 'Animal Bites':'dog bite cat bite',
 'Breathing Problems':'shortness of breath difficulty breathing',
 'Asthma':'asthma attack wheezing',
 'Foodborne Illness':'food poisoning ate bad food',
 'Diarrhea':'loose stools watery stools',
 'Nausea and Vomiting':'throwing up sick to stomach',
 'Gastrointestinal Bleeding':'blood in vomit bloody stool',
 'Urinary Tract Infections':'uti burning urination',
 'Kidney Stones':'flank pain kidney stone',
 'Hypoglycemia':'low blood sugar',
 'Hyperglycemia':'high blood sugar',
 'Diabetes':'blood sugar insulin',
 'Fainting':'passed out fainted',
 'Dizziness and Vertigo':'room spinning dizzy',
 'Pulmonary Embolism':'blood clot in lung',
 'Depression':'feeling depressed',
 'Anxiety':'panic worry fear',
}

CANONICAL_MANUAL = {
  'First Aid':'https://medlineplus.gov/firstaid.html',
  'Bleeding':'https://medlineplus.gov/bleeding.html',
  'Burns':'https://medlineplus.gov/burns.html',
  'Anaphylaxis':'https://medlineplus.gov/anaphylaxis.html',
  'Animal Bites':'https://medlineplus.gov/animalbites.html',
  'Asthma':'https://medlineplus.gov/asthma.html',
  'Heat Illness':'https://medlineplus.gov/heatillness.html',
}

# Sources held as citations/links only; no wholesale CDC or NHS article copying.
SUPPLEMENTAL_LINKS = {
 'Heat Illness': [('CDC','https://www.cdc.gov/niosh/heat-stress/about/illnesses.html'),('NHS','https://www.nhs.uk/conditions/heat-exhaustion-heatstroke/')],
 'Burns': [('NHS','https://www.nhs.uk/conditions/burns-and-scalds/')],
 'Anaphylaxis': [('NHS','https://www.nhs.uk/conditions/anaphylaxis/')],
}
