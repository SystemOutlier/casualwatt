from energy import SESSION

print("type:", type(SESSION))
print("has __enter__:", hasattr(SESSION, "__enter__"))
print("has start:", hasattr(SESSION, "start"))
print("has stop:", hasattr(SESSION, "stop"))
print("has result:", hasattr(SESSION, "result"))

print("dir:")
for name in dir(SESSION):
    if not name.startswith("_"):
        print(" -", name)

if hasattr(SESSION, "__enter__"):
    with SESSION as s:
        print("inside session type:", type(s))
        print("inside dir:")
        for name in dir(s):
            if not name.startswith("_"):
                print(" -", name)
        print("result:", getattr(s, "result", None))