# seekdb 查询记录

模块一共执行了 19647 条 seekdb 语句。
下面是去重后的语句（每条附一次真实执行的结果行数）。

## rows=9  mode=fulltext

```sql
SELECT * FROM sdd_spec WHERE MATCH(content) AGAINST (%s) ORDER BY updated_at DESC LIMIT %s
```

参数（截断）：`["matches signature types string predicate filter JMESPathTypeError regex", "12"]`

## rows=12  mode=select

```sql
SELECT * FROM sdd_spec WHERE spec_id = %s ORDER BY section_id
```

参数（截断）：`["SPEC-JP-FN-001"]`

## rows=41  mode=select

```sql
SELECT * FROM sdd_code WHERE file_path = %s ORDER BY source_line
```

参数（截断）：`["jmespath/functions.py"]`

## rows=8  mode=fulltext

```sql
SELECT * FROM sdd_code WHERE MATCH(content) AGAINST (%s) ORDER BY updated_at DESC LIMIT %s
```

参数（截断）：`["matches signature types string predicate filter JMESPathTypeError regex", "8"]`

## rows=6  mode=select

```sql
SELECT * FROM sdd_test WHERE file_path = %s ORDER BY source_line
```

参数（截断）：`["tests/test_matches.py"]`

## rows=8  mode=fulltext

```sql
SELECT * FROM sdd_test WHERE MATCH(content) AGAINST (%s) ORDER BY updated_at DESC LIMIT %s
```

参数（截断）：`["matches signature types string predicate filter JMESPathTypeError regex", "8"]`

## rows=0  mode=delete

```sql
DELETE ... WHERE source_path = %s
```

参数（截断）：`["minimax/specs/jmespath-matches.md"]`

## rows=1  mode=upsert

```sql
INSERT INTO sdd_spec (spec_id, section_id, kind, title, content, source_path, source_line, doc_title, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE kind = VALUES(kind), title = VALUES(title), content = VALUES(content), source_path = VALUES(source_path), source_line = VALUES(source_line), doc_title = VALUES(doc_title), updated_at = VALUES(updated_at)
```

参数（截断）：`["SPEC-JP-FN-001", "R1", "note", "matches 必须是恰好两个字符串参数", "matches 必须是恰好两个字符串参数\n`matches` 注册为内建函数，签名为两个 `string` 类型的参数\n（`@signature({'ty...", "minimax/specs/jmespath-matches.md", "40", "matches(subject, pattern) 正则谓词函数", "2026-10-28 21:56:49.133721"]`

## rows=1  mode=upsert

```sql
INSERT INTO sdd_code (file_path, symbol, kind, signature, content, source_path, source_line, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE kind = VALUES(kind), signature = VALUES(signature), content = VALUES(content), source_path = VALUES(source_path), source_line = VALUES(source_line), updated_at = VALUES(updated_at)
```

参数（截断）：`["bin/jp.py", "main", "function", "def main()", "def main():\n    parser = argparse.ArgumentParser()\n    parser.add_argument('e...", "minimax/sample_project/jmespath/bin/jp.py", "12", "2026-10-28 21:56:49.533285"]`

## rows=1  mode=upsert

```sql
INSERT INTO sdd_test (test_id, file_path, name, target, content, source_path, source_line, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE file_path = VALUES(file_path), name = VALUES(name), target = VALUES(target), content = VALUES(content), source_path = VALUES(source_path), source_line = VALUES(source_line), updated_at = VALUES(updated_at)
```

参数（截断）：`["extra/test_hypothesis.py::test_lexer_api", "extra/test_hypothesis.py", "test_lexer_api", "extra/test_hypothesis.py::test_lexer_api", "def test_lexer_api(expr):\n    try:\n        tokens = list(lexer.Lexer().tokeni...", "minimax/sample_project/jmespath/extra/test_hypothesis.py", "39", "2026-10-28 21:56:56.393424"]`

## rows=1  mode=select

```sql
SELECT (SELECT COUNT(*) FROM sdd_spec) AS specs, (SELECT COUNT(*) FROM sdd_code) AS code, (SELECT COUNT(*) FROM sdd_test) AS tests
```
