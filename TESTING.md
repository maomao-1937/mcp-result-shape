# Testing

From the repository root, run these commands with Python 3.11 or later.

```sh
python -B -m unittest discover -s tests -v
python -B ci_checks.py
```

The CLI suite checks both error policies, result extensions, exact mathematical integer classification, member ordering and limits, strict JSON throughout each document, input path guards, file size and descriptor checks, and quiet failure for a closed stdout pipe. The FIFO test uses a real FIFO where `os.mkfifo` is available and simulates FIFO metadata elsewhere to verify rejection before open. CI runs on Ubuntu and Windows with Python 3.11.

The synthetic examples exercise exits 0, 1 and 2. `ci_checks.py` compares their exact report fields, exit codes and empty stderr.
