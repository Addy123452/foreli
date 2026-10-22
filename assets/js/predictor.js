/* Foreli Predictor — demo fixtures + transparent 1X2 model.
 *
 * DEMO DATA ONLY: every fixture below is fictional and the probabilities are
 * illustrative model output, not real predictions. Replace DEMO_MATCHES with
 * data from a real provider to use this UI with live matches.
 */
(function () {
  'use strict';

  // Fictional fixtures (demo). `strength` is a 0..1 team-strength estimate.
  var DEMO_MATCHES = [
    {
      id: 'd1', competition: 'Demo League', kickoff: 'Today · 19:30',
      home: { name: 'Demo City', strength: 0.72 },
      away: { name: 'Sample United', strength: 0.55 },
    },
    {
      id: 'd2', competition: 'Demo League', kickoff: 'Today · 21:00',
      home: { name: 'Example Rovers', strength: 0.48 },
      away: { name: 'Placeholder Athletic', strength: 0.66 },
    },
    {
      id: 'd3', competition: 'Demo Cup', kickoff: 'Tomorrow · 18:00',
      home: { name: 'Test Town', strength: 0.60 },
      away: { name: 'Mock Wanderers', strength: 0.61 },
    },
    {
      id: 'd4', competition: 'Demo Cup', kickoff: 'Tomorrow · 20:15',
      home: { name: 'Fictional FC', strength: 0.80 },
      away: { name: 'Demo City', strength: 0.72 },
    },
  ];

  var HOME_ADVANTAGE = 0.10;
  var DRAW_BONUS = 0.02;
  var TEMPERATURE = 10;

  function softmax(scores) {
    var max = Math.max.apply(null, scores);
    var exps = scores.map(function (s) { return Math.exp(TEMPERATURE * (s - max)); });
    var sum = exps.reduce(function (a, b) { return a + b; }, 0);
    return exps.map(function (e) { return e / sum; });
  }

  // Transparent three-way model: softmax(home, draw, away) -> sums to 1.
  function predict(match) {
    var homeScore = match.home.strength + HOME_ADVANTAGE;
    var awayScore = match.away.strength;
    var drawScore = (match.home.strength + match.away.strength) / 2 + DRAW_BONUS;
    var p = softmax([homeScore, drawScore, awayScore]);
    var probs = { home: p[0], draw: p[1], away: p[2] };

    var winner = 'home';
    if (probs.draw > probs[winner]) winner = 'draw';
    if (probs.away > probs[winner]) winner = 'away';

    var diff = match.home.strength - match.away.strength;
    var factors = [
      'Home strength ' + match.home.strength.toFixed(2) + ' vs away ' + match.away.strength.toFixed(2),
      'Home advantage +' + HOME_ADVANTAGE.toFixed(2),
      (diff >= 0 ? 'Home edge' : 'Away edge') + ' ' + Math.abs(diff).toFixed(2),
    ];

    return { probs: probs, winner: winner, confidence: probs[winner], factors: factors };
  }

  function pct(x) { return Math.round(x * 100) + '%'; }

  function card(match) {
    var r = predict(match);
    var p = r.probs;
    var top = r.winner;

    function probCell(key, label) {
      var isTop = key === top ? ' top' : '';
      return '<div class="prob' + isTop + '">' +
        '<div class="prob-label">' + label + '</div>' +
        '<div class="prob-value">' + pct(p[key]) + '</div></div>';
    }

    var factors = r.factors.map(function (f) {
      return '<span class="factor">' + f + '</span>';
    }).join('');

    return '<article class="match" data-id="' + match.id + '">' +
      '<div class="match-top"><span class="competition">' + match.competition + '</span>' +
      '<span class="kickoff">' + match.kickoff + '</span></div>' +
      '<div class="teams">' +
      '<div class="team home"><div class="team-name">' + match.home.name + '</div>' +
      '<div class="team-strength">strength ' + match.home.strength.toFixed(2) + '</div></div>' +
      '<div class="vs">vs</div>' +
      '<div class="team away"><div class="team-name">' + match.away.name + '</div>' +
      '<div class="team-strength">strength ' + match.away.strength.toFixed(2) + '</div></div>' +
      '</div>' +
      '<div class="probs">' +
      probCell('home', 'Home') + probCell('draw', 'Draw') + probCell('away', 'Away') +
      '</div>' +
      '<div class="bar"><div class="bar-fill" style="width:' + pct(r.confidence) + '"></div></div>' +
      '<div class="confidence">Most likely: <b>' +
      (top === 'home' ? match.home.name : top === 'away' ? match.away.name : 'Draw') +
      '</b> · confidence <b>' + pct(r.confidence) + '</b></div>' +
      '<div class="factors">' + factors + '</div>' +
      '</article>';
  }

  var grid = document.getElementById('matchGrid');
  if (grid) {
    grid.innerHTML = DEMO_MATCHES.map(card).join('');
  }
})();
