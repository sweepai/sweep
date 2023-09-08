#!/bin/bash

optional_secret_names=('bot-token' 'posthog' 'anthropic' 'e2b' 'discord' 'gdrp' 'activeloop' 'activeloop_token')

for name in "${optional_secret_names[@]}"; do
	modal secret create "$name" EMPTY=EMPTY
done

echo "empty secrets creation complete"
