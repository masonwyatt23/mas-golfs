/* Mas Golfs — realistic placeholder data for standalone preview.
   This is the browser copy of shared/placeholder-data.json (same values).
   When a graphic runs inside NodeCG, the real replicants replace this data.
   Keep the two in sync when the placeholder round changes. */
window.MAS_PLACEHOLDER = {
  "roundState": {
    "golfer": "Mas",
    "round": 47,
    "hole": 12,
    "hole_par": 3,
    "score_to_par": -2,
    "thru": 11,
    "target_score": 59,
    "handicap": "+3.1",
    "last10_avg": 70.4,
    "all_time_score": -41,
    "course_record": 63,
    "best_round": 64,
    "current_hole": { "name": "The Picture", "par": 3, "yards": 172 },
    "scorecard": [
      { "hole": 1, "par": 4, "score": 4, "putts": 2 },
      { "hole": 2, "par": 5, "score": 5, "putts": 2 },
      { "hole": 3, "par": 3, "score": 2, "putts": 1 },
      { "hole": 4, "par": 4, "score": 4, "putts": 2 },
      { "hole": 5, "par": 4, "score": 3, "putts": 1 },
      { "hole": 6, "par": 4, "score": 4, "putts": 2 },
      { "hole": 7, "par": 5, "score": 5, "putts": 2 },
      { "hole": 8, "par": 3, "score": 3, "putts": 2 },
      { "hole": 9, "par": 4, "score": 4, "putts": 1 },
      { "hole": 10, "par": 4, "score": 4, "putts": 2 },
      { "hole": 11, "par": 5, "score": 4, "putts": 1 }
    ],
    "stats": { "fairways": "6/11", "gir": "7/11", "putts": 19, "up_and_downs": "2/3" },
    "streak": { "birdies": 2, "bogey_free": 5 },
    "coins": {
      "prediction_open": true,
      "question": "Birdie or better on 12?",
      "odds": { "yes": 2.4, "no": 1.6 }
    }
  },
  "shotData": {
    "club": "7-iron",
    "ball_speed_mph": 132,
    "launch_deg": 19,
    "spin_rpm": 6800,
    "apex_ft": 78,
    "carry_yds": 166,
    "total_yds": 172,
    "target_yards": 172,
    "shape": "draw",
    "contact": "pure",
    "dist_to_pin_ft": 12,
    "lie": "green"
  },
  "prediction": {
    "question": "Birdie or better on 12?",
    "odds": { "yes": 2.4, "no": 1.6 },
    "pool_coins": 1840,
    "closes_in_s": 45,
    "open": true
  },
  "lastShot": "7-iron from 172 — 12 ft, birdie putt",
  "leaderboard": [
    { "rank": 1, "round": 41, "score": 63, "to_par": -9, "date": "Nov 10" },
    { "rank": 2, "round": 38, "score": 64, "to_par": -8, "date": "Nov 9" },
    { "rank": 3, "round": 44, "score": 65, "to_par": -7, "date": "Nov 11" },
    { "rank": 4, "round": 35, "score": 66, "to_par": -6, "date": "Nov 7" },
    { "rank": 5, "round": 46, "score": 66, "to_par": -6, "date": "Nov 11" },
    { "rank": 6, "round": 29, "score": 67, "to_par": -5, "date": "Nov 5" },
    { "rank": 7, "round": 33, "score": 67, "to_par": -5, "date": "Nov 6" },
    { "rank": 8, "round": 40, "score": 68, "to_par": -4, "date": "Nov 9" },
    { "rank": 9, "round": 42, "score": 68, "to_par": -4, "date": "Nov 10" },
    { "rank": 10, "round": 27, "score": 69, "to_par": -3, "date": "Nov 4" }
  ],
  "seasonStats": {
    "driving_yds": 268,
    "fairways_pct": 58,
    "gir_pct": 61,
    "putts_per_round": 29.1,
    "scoring_avg": 70.4
  },
  "learningFix": {
    "leak": "approach_125_150",
    "strokes_lost": 1.8,
    "adjustment": "Aim 5 yards right of pin from 125–150; dispersion is left-biased"
  },
  "holeInfo": {
    "hole": 12,
    "name": "The Picture",
    "par": 3,
    "yards": 172,
    "wind_mph": 12,
    "wind_dir": "→",
    "pin": "back-left",
    "elevation_ft": -22
  },
  // Wyatt National v3 — par 72, 7,602 yards (front 3,808 / back 3,794).
  // Full course table, so every graphic can read hole data from one place.
  "course": {
    "name": "Wyatt National",
    "par": 72,
    "yards": 7602,
    "front_yards": 3808,
    "back_yards": 3794,
    "holes": [
      { "hole": 1, "name": "The Handshake", "par": 4, "yards": 432 },
      { "hole": 2, "name": "The Reach", "par": 5, "yards": 612 },
      { "hole": 3, "name": "The Postage Stamp", "par": 3, "yards": 196 },
      { "hole": 4, "name": "The Examination", "par": 4, "yards": 476 },
      { "hole": 5, "name": "The Temptation", "par": 4, "yards": 392 },
      { "hole": 6, "name": "The Dogleg", "par": 4, "yards": 452 },
      { "hole": 7, "name": "The Valley", "par": 5, "yards": 586 },
      { "hole": 8, "name": "The Long One", "par": 3, "yards": 238 },
      { "hole": 9, "name": "The Return", "par": 4, "yards": 424 },
      { "hole": 10, "name": "The Turn", "par": 4, "yards": 440 },
      { "hole": 11, "name": "The Monster", "par": 5, "yards": 624 },
      { "hole": 12, "name": "The Picture", "par": 3, "yards": 172 },
      { "hole": 13, "name": "The Grind", "par": 4, "yards": 482 },
      { "hole": 14, "name": "The Gambler", "par": 4, "yards": 406 },
      { "hole": 15, "name": "The Eagle Chance", "par": 5, "yards": 578 },
      { "hole": 16, "name": "The Test", "par": 3, "yards": 214 },
      { "hole": 17, "name": "The Penultimate", "par": 4, "yards": 448 },
      { "hole": 18, "name": "The Closer", "par": 4, "yards": 430 }
    ]
  },
  "lowerThirds": {
    "shot": {
      "variant": "shot",
      "title": "7-IRON · 172 YDS",
      "body": "Ball 132 mph · Launch 19° · Spin 6,800 · Apex 78 ft"
    },
    "holeResult": {
      "variant": "holeResult",
      "title": "HOLE 12 — BIRDIE",
      "body": "-3 thru 12 · 2 putts · Up-and-down ✓"
    },
    "milestone": {
      "variant": "milestone",
      "title": "COURSE RECORD PACE",
      "body": "Mas is -4 thru 12, record is 63"
    }
  }
};
