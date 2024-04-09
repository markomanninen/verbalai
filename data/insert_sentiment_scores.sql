-- SQL Inserts for Sentiment Scores
BEGIN TRANSACTION;

INSERT INTO sentiment_scores (dialogue_unit_id, positive_score, negative_score) VALUES
(1, 0.75, 0.25), -- Related to the first dialogue unit of discussion 1
(2, 0.85, 0.15), -- Related to the second dialogue unit of discussion 1
(3, 0.90, 0.10), -- Related to the first dialogue unit of discussion 2
(4, 0.95, 0.05), -- Related to the second dialogue unit of discussion 2
(5, 0.88, 0.12), -- Related to the dialogue unit of discussion 3
(6, 0.80, 0.20), -- Related to the dialogue unit of discussion 4
(7, 0.92, 0.08); -- Related to the dialogue unit of discussion 5

COMMIT;
