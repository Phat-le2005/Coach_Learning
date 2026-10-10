-- Execute ONLY on a disposable PostgreSQL DB. TEMP + ROLLBACK. Not migration.
BEGIN;
CREATE TEMP TABLE step_reorder_probe (
 id INT PRIMARY KEY, attempt_id INT NOT NULL,
 step_index INT NOT NULL CHECK (step_index >= 1),
 is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE UNIQUE INDEX probe_active_idx ON step_reorder_probe(attempt_id,step_index) WHERE is_deleted=FALSE;
INSERT INTO step_reorder_probe VALUES (1,9,1,FALSE),(2,9,2,FALSE),(3,9,3,FALSE);
UPDATE step_reorder_probe SET step_index=CASE id WHEN 1 THEN 11 WHEN 2 THEN 12 WHEN 3 THEN 13 END WHERE id IN (1,2,3);
UPDATE step_reorder_probe SET step_index=CASE id WHEN 1 THEN 2 WHEN 2 THEN 1 WHEN 3 THEN 3 END WHERE id IN (1,2,3);
DO $$ BEGIN
 IF (SELECT step_index FROM step_reorder_probe WHERE id=1)<>2 OR (SELECT step_index FROM step_reorder_probe WHERE id=2)<>1
 THEN RAISE EXCEPTION 'swap mismatch'; END IF;
END $$;
UPDATE step_reorder_probe SET is_deleted=TRUE WHERE id=2;
INSERT INTO step_reorder_probe VALUES(4,9,1,FALSE);
UPDATE step_reorder_probe SET step_index=4,is_deleted=FALSE WHERE id=2;
DO $$ BEGIN
 IF (SELECT COUNT(*) FROM step_reorder_probe WHERE attempt_id=9 AND NOT is_deleted)<>4
 THEN RAISE EXCEPTION 'restore mismatch'; END IF;
END $$;
ROLLBACK;
