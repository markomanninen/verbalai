-- SQL Inserts for Dialogue Units
BEGIN TRANSACTION;

-- Dialogue Units for Discussion 1: Technology Advances in 2023
INSERT INTO dialogue_units (prompt, response, intent, timestamp, discussion_id) VALUES
('How has technology impacted our daily lives?', 'Technology has vastly improved our daily lives through advancements in communication, healthcare, and transportation.', 'impact_discussion', '2023-04-01 09:15:00', '1'),
('What are the latest breakthroughs in technology?', 'Recent breakthroughs include quantum computing, 5G cellular networks, and biometric technology.', 'latest_breakthroughs', '2023-04-01 09:30:00', '1');

-- Dialogue Units for Discussion 2: Sustainability and Green Energy
INSERT INTO dialogue_units (prompt, response, intent, timestamp, discussion_id) VALUES
('Why is green energy important?', 'Green energy is crucial for reducing carbon emissions and fighting climate change.', 'importance_of_green_energy', '2023-04-10 11:15:00', '2'),
('What are some renewable energy sources?', 'Renewable energy sources include solar power, wind energy, hydroelectric energy, and geothermal power.', 'renewable_sources', '2023-04-10 11:30:00', '2');

-- Dialogue Units for Discussion 3: Exploring the Depths of Space in the 21st Century
INSERT INTO dialogue_units (prompt, response, intent, timestamp, discussion_id) VALUES
('What makes Mars exploration a priority?', 'Mars has water, an essential element for life, making it a prime candidate for exploration and potential colonization.', 'mars_exploration', '2023-04-15 15:15:00', '3');

-- Dialogue Units for Discussion 4: The Future of AI and Machine Learning
INSERT INTO dialogue_units (prompt, response, intent, timestamp, discussion_id) VALUES
('How will AI change the workforce?', 'AI will automate routine tasks, create new job categories, and require a shift in skills for the workforce.', 'ai_impact', '2023-04-20 14:15:00', '4');

-- Dialogue Units for Discussion 5: Advancements in Renewable Energy
INSERT INTO dialogue_units (prompt, response, intent, timestamp, discussion_id) VALUES
('Can renewable energy replace fossil fuels?', 'With advancements in technology and increased capacity, renewable energy has the potential to significantly replace fossil fuels.', 'renewable_vs_fossil', '2023-04-25 09:15:00', '5');

COMMIT;
