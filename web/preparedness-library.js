'use strict';

window.LifeLinePreparednessLibrary = Object.freeze({
  version: 'nps-ten-essentials-2026-05-28-v1',
  source: Object.freeze({
    id: 'nps-ten-essentials',
    publisher: 'National Park Service',
    title: 'Ten Essentials',
    url: 'https://www.nps.gov/articles/10essentials.htm',
    updated: 'May 28, 2026',
    accessed: 'October 17, 2026'
  }),
  // Concrete examples paraphrased from NPS; first-aid contents use Red Cross.
  supplies: Object.freeze({
    navigation: ['Paper map of the area', 'Compass', 'GPS device or downloaded map', 'Spare batteries for navigation devices'],
    sun: ['Sunscreen', 'Sunglasses', 'Sun hat', 'Long-sleeved sun-protection clothing'],
    layers: ['Extra jacket or warm layer', 'Rain shell', 'Warm hat', 'Gloves for expected conditions'],
    light: ['Headlamp or flashlight', 'Spare batteries'],
    'first-aid': ['Adhesive bandages in assorted sizes', 'Sterile gauze pads and absorbent dressings', 'Roller and triangular bandages', 'Medical adhesive cloth tape', 'Nonlatex gloves', 'Antiseptic wipes', 'Instant cold compress', 'Emergency first-aid instruction booklet'],
    repair: ['Duct tape for equipment repairs', 'Repair supplies specific to your equipment'],
    food: ['Granola or energy bars', 'Trail mix or nuts, if suitable for your allergies', 'Extra ready-to-eat food that needs no cooking'],
    water: ['Drinking water in suitable containers', 'Water filter or other water-treatment supplies appropriate to the trip'],
    shelter: ['Emergency blanket', 'Tarp, bivy sack or tent appropriate to your trip'],
    'life-jacket': ['Properly fitting life jacket suitable for the water activity'],
    insects: ['Insect repellent, used according to its product label'],
    communication: ['Two-way satellite messenger appropriate to your communication plan']
  }),
  firstAidSource: Object.freeze({
    title: 'Make a First Aid Kit',
    publisher: 'American Red Cross',
    url: 'https://www.redcross.org/get-help/how-to-prepare-for-emergencies/anatomy-of-a-first-aid-kit.html'
  }),
  items: Object.freeze([
    { id: 'navigation', title: 'Navigation supplies', rationale: 'Pack a physical map and compass, plus a GPS device and spare batteries as appropriate. NPS includes navigation aids for finding your way.' },
    { id: 'sun', title: 'Sun protection', rationale: 'Consider sunglasses, sunscreen, a hat and long sleeves. NPS lists these as protection from sun exposure.' },
    { id: 'layers', title: 'Extra clothing and weather layers', rationale: 'Include layers such as a jacket, gloves and rain shell for changing conditions, as described by NPS.' },
    { id: 'light', title: 'Headlamp or flashlight', rationale: 'Pack a light and spare batteries. NPS includes illumination for times when daylight is not available.' },
    { id: 'first-aid', title: 'First aid kit', rationale: 'Include a premade first aid kit and check expiry dates. This is a supply reminder only, with no treatment or medication advice.' },
    { id: 'repair', title: 'Repair tape', rationale: 'Pack repair tape, such as duct tape, for basic equipment repairs. This checklist uses the tape option from the NPS repair category, not sharp tools.' },
    { id: 'food', title: 'Extra no-cook food', rationale: 'NPS recommends an extra day of food that does not require cooking, in case a trip takes longer than expected.' },
    { id: 'water', title: 'Drinking water and water treatment supplies', rationale: 'NPS includes drinking water and treatment supplies in hydration planning. Amounts and treatment instructions are not provided here.' },
    { id: 'shelter', title: 'Emergency shelter', rationale: 'Consider a tent, tarp, bivy or emergency blanket. NPS includes shelter for unexpected exposure.' },
    { id: 'life-jacket', title: 'Life jacket', rationale: 'NPS lists a life jacket among additional activity-specific items. Consider it for water activities; this checklist does not assess water safety.', activitySpecific: true },
    { id: 'insects', title: 'Insect repellent', rationale: 'NPS lists bug spray among additional items. Consider it where insects are expected; follow the product label.', activitySpecific: true },
    { id: 'communication', title: 'Two-way satellite messenger', rationale: 'NPS lists a two-way satellite messenger among additional items. Consider communication needs for your activity; packing one does not guarantee contact or rescue.', activitySpecific: true }
  ].map((item) => Object.freeze({ ...item, sourceId: 'nps-ten-essentials' })))
});
