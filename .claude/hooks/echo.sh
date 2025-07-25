#!/bin/bash

# Running claude verbose / log mode with ctrl+r will show log output with hook success/failure.

echo "hi iain foo.txt has been created!"
# any exit code that's not error 2 will get claude to report to chat and continue
exit 3
# get the conversation from claude
