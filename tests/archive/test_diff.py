from sweepai.utils.diff import generate_new_file_from_patch

code = """
import (
	"errors"
	"path/filepath"
	"strings"
)

type command struct {
	path, lang string
	start, end *string
}

func parseCommand(s string) (*command, error) {
log.Debug("parseCommand called with input: ", s)
log.Debug("Trimming spaces from input string")
s = strings.TrimSpace(s)
log.Debug("Checking if argument list is in parentheses")
if len(s) < 2 || s[0] != '(' || s[len(s)-1] != ')' {
		return nil, errors.New("argument list should be in parenthesis")
	}
"""

code = """
import (
	"errors"
	"path/filepath"
	"strings"
)

type command struct {
	path, lang string
	start, end *string
}

func parseCommand(s string) (*command, error) {
	log.Debug("parseCommand called with input: ", s)
	s = strings.TrimSpace(s)
	log.Debug("Checking if argument list is in parentheses")
	if len(s) < 2 || s[0] != '(' || s[len(s)-1] != ')' {
		return nil, errors.New("argument list should be in parenthesis")
	}
"""

diff = """
<<<< ORIGINAL
log.Debug("parseCommand called with input: ", s)
====
log.Debug("parseCommand called with input: ", s)
log.Debug("Trimming spaces from input string")
>>>> UPDATED
"""


# print(len(detect_indent(code)))
print(generate_new_file_from_patch(diff, code)[0])
