# seekdb 可执行文件

把 seekdb 1.4 的服务端二进制放到本目录（或 `backend/seekdb/`），文件名 `seekdb.exe`
（Windows）/ `seekdb`（Linux），然后运行 `npm run setup:seekdb`。

二进制来自 `pylibseekdb` wheel：

```bash
python -m pip install pylibseekdb==1.4.0.post2
python -c "import pylibseekdb,os;print(os.path.join(os.path.dirname(pylibseekdb.__file__),'..','pylibseekdb.libs','seekdb.exe'))"
```

也可以直接设置 `SEEKDB_BIN` 指向已有路径。该二进制体积较大，不纳入版本库。
