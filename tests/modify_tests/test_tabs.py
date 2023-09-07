from tests.modify_tests.modify_test import run_test

run_test(
    old_file="""
	wow
		very cool
			much wow
""",
    message="""<<<< ORIGINAL
very cool
====
[ works ]
>>>> UPDATED""",
)
