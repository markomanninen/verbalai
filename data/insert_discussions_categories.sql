-- SQL Inserts for Discussions
BEGIN TRANSACTION;

INSERT INTO discussions (id, title, starttime, endtime, featured) VALUES
('1', 'Technology Advances in 2023', '2023-04-01 09:00:00', '2023-04-01 10:00:00', 1),
('2', 'Sustainability and Green Energy', '2023-04-10 11:00:00', '2023-04-10 12:00:00', 0),
('3', 'Exploring the Depths of Space in the 21st Century', '2023-04-15 15:00:00', '2023-04-15 16:00:00', 1),
('4', 'The Future of AI and Machine Learning', '2023-04-20 14:00:00', '2023-04-20 15:30:00', 0),
('5', 'Advancements in Renewable Energy', '2023-04-25 09:00:00', '2023-04-25 10:00:00', 1);

-- SQL Inserts for Categories Linked to Discussions
INSERT INTO categories (name, score, discussion_id) VALUES
('Technology', 0.95, '1'),
('Innovation', 0.9, '1'),
('Environment', 0.88, '2'),
('Sustainability', 0.92, '2'),
('Space Exploration', 0.89, '3'),
('Astrophysics', 0.85, '3'),
('Artificial Intelligence', 0.87, '4'),
('Machine Learning', 0.93, '4'),
('Renewable Energy', 0.9, '5'),
('Solar Power', 0.88, '5');

COMMIT;