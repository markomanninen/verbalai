-- SQL Inserts for Topics
BEGIN TRANSACTION;

INSERT INTO topics (id, name) VALUES
(1, 'Technology'),
(2, 'Sustainability'),
(3, 'Environment'),
(4, 'Quantum Computing'),
(5, 'Technology Trends'),
(6, 'Recycling'),
(7, 'Energy Conservation'),
(8, 'Space Exploration'),
(9, 'Astrophysics'),
(10, 'Artificial Intelligence'),
(11, 'Machine Learning'),
(12, 'Renewable Energy'),
(13, 'Solar Power');

-- Assuming dialogue units and topics have been inserted
-- SQL Inserts for Linking Dialogue Units to Topics (Dialogue Unit Topics)
INSERT INTO dialogue_unit_topics (dialogue_unit_id, topic_id) VALUES
(1, 4), -- Quantum Computing topic linked to the first dialogue unit of discussion 1
(1, 5), -- Technology Trends topic linked to the first dialogue unit of discussion 1
(2, 1), -- Technology topic linked to the second dialogue unit of discussion 1
(3, 6), -- Recycling topic linked to the first dialogue unit of discussion 2
(3, 7), -- Energy Conservation topic linked to the first dialogue unit of discussion 2
(4, 12), -- Renewable Energy topic linked to the second dialogue unit of discussion 2
(4, 13), -- Solar Power topic linked to the second dialogue unit of discussion 2
(5, 8), -- Space Exploration topic linked to the dialogue unit of discussion 3
(5, 9), -- Astrophysics topic linked to the dialogue unit of discussion 3
(6, 10), -- Artificial Intelligence topic linked to the dialogue unit of discussion 4
(6, 11), -- Machine Learning topic linked to the dialogue unit of discussion 4
(7, 12); -- Renewable Energy topic linked to the dialogue unit of discussion 5

COMMIT;
