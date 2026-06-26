# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Agentic chat-action interfaces (W28M-1605).

Additive package: turns a single natural-language instruction into a
capability invocation (intent-parse -> IDAM gate -> invoke -> confirm) without
modifying the conversational ``chat_tool`` or the ``TransactionalExecutor``
graph. Consumed by the A2A ``run_document_process`` skill.
"""
