UPDATE study_resources
SET platform_path = 'Rodha Free CAT → Quant playlist → select the mapped topic',
    updated_at = CURRENT_TIMESTAMP
WHERE id = 'rodha-cat-free' AND platform_path IS NULL;
