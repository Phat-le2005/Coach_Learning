from neo4j import GraphDatabase

class GraphStore:
    def __init__(self, uri: str, username: str, password: str, database: str = "neo4j"):
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        self.database = database

    def close(self):
        self.driver.close()

    def initialize(self):
        queries = [
            "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (n:Document) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT question_id IF NOT EXISTS FOR (n:Question) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT solution_id IF NOT EXISTS FOR (n:Solution) REQUIRE n.id IS UNIQUE",
        ]
        with self.driver.session(database=self.database) as session:
            for query in queries:
                session.run(query)

    def save(self, document_id: str, filename: str, questions: list[dict]):
        with self.driver.session(database=self.database) as session:
            session.execute_write(self._save_tx, document_id, filename, questions)

    @staticmethod
    def _save_tx(tx, document_id, filename, questions):
        tx.run(
            "MERGE (d:Document {id:$id}) SET d.filename=$filename",
            id=document_id, filename=filename
        )
        for q in questions:
            tx.run(
                '''
                MATCH (d:Document {id:$doc_id})
                MERGE (q:Question {id:$qid})
                SET q.text=$qtext, q.needs_review=$review
                MERGE (d)-[:CONTAINS]->(q)
                ''',
                doc_id=document_id, qid=q["question_id"],
                qtext=q["question_text"], review=q["needs_review"]
            )
            if q["solution_text"]:
                sid = "sol-" + q["question_id"]
                tx.run(
                    '''
                    MATCH (q:Question {id:$qid})
                    MERGE (s:Solution {id:$sid})
                    SET s.raw_text=$stext, s.verified=false
                    MERGE (q)-[:HAS_SOLUTION]->(s)
                    ''',
                    qid=q["question_id"], sid=sid, stext=q["solution_text"]
                )
            for page in q["pages"]:
                tx.run(
                    '''
                    MATCH (q:Question {id:$qid})
                    MERGE (p:SourcePage {id:$pid})
                    SET p.page_number=$page, p.document_id=$doc_id
                    MERGE (q)-[:FOUND_ON]->(p)
                    ''',
                    qid=q["question_id"], pid=f"{document_id}-p{page}",
                    page=page, doc_id=document_id
                )
