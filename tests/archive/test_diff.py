from sweepai.utils.diff import detect_indent

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
    log.Debug("Trimming spaces from input string")
    s = strings.TrimSpace(s)
    log.Debug("Checking if argument list is in parentheses")
    if len(s) < 2 || s[0] != '(' || s[len(s)-1] != ')' {
        return nil, errors.New("argument list should be in parenthesis")
    }
"""

indent = detect_indent(code)

# print(len(detect_indent(code)))
print()