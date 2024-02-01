// @ts-ignore
import JavaScript from "tree-sitter-javascript";
// @ts-ignore
import Python from "tree-sitter-python";
import { checkCode, checkTree, parseCode } from "./tree";

const sourceCode = 'let x = 1; console.log(x);';
const tree = parseCode(sourceCode, JavaScript);

const additionalOpening = `function bar() {
function bar() {
    console.log('bar');
}`;
const unfinishedFunction = `function bar()
function bar() {
    console.log('bar');
}`;
const unfinishedFunction2 = `function bar()
console.log('bar');
function bar() {
    console.log('bar');
}`;
const additionalClosing = `function bar() {
    console.log('bar');
}
}`;
const brokenCodes = [additionalOpening, unfinishedFunction, unfinishedFunction2, additionalClosing]
const brokenTrees = brokenCodes.map((code) => parseCode(code, JavaScript));

const codeExamplesByLanguage: {[key in string]: string} = {
    "js": `let x = 1;
    console.log(x);
    function foo() {
        console.log('foo');
    }`,
    "jsx": `const App = () => (
        <div>
          <h1>Hello, Sweep!</h1>
        </div>
      );

      export default App;`,
    "ts": `interface User {
        name: string;
        id: number;
    }`,
    "tsx": `const App: React.FC = () => (
        <div>
          <h1>Hello, Sweep!</h1>
        </div>
      );

      export default App;`,
    "py": `def foo():
    print("hello")`,
    "rust": `fn main() {
        println!("Hello, world!");
    }`,
    "html": `<!DOCTYPE html>
    <html>
    <body>
    Hello world
    </body>
    </html>`
}

const badPythonCode = `def foo():

print("hello")`

describe('checkCode', () => {
    it('should return a tree', () => {
        expect(tree.rootNode.type).toBe('program');
    });

    it('should identify broken trees', () => {
        for (const brokenTree of brokenTrees) {
            console.log(checkTree(brokenTree))
            expect(checkTree(brokenTree).length > 0).toBe(true);
        }
    });

    // it('should identify broken python', () => {
    //     console.log(parseCode(badPythonCode, Python).rootNode.toString())
    //     expect(checkCode(badPythonCode, 'main.py').length > 0).toBe(true);
    // })

    for (const language in codeExamplesByLanguage) {
        it(`parses ${language}`, () => {
            const results = checkCode(codeExamplesByLanguage[language], `main.${language}`);
            expect(results).toBe('');
        })
    }

    // check that the wrong language returns a non-empty string
    const parserLanguages = ['js', 'py', 'rust']
    for (const index in parserLanguages) {
        const parserLanguage = parserLanguages[index];
        for (const language in codeExamplesByLanguage) {
            if (language.startsWith(parserLanguage)) {
                // startswith catches js and jsx, ts and tsx
                continue;
            }
            it(`should return an error for parsing ${language} with ${parserLanguage}`, () => {
                const results = checkCode(codeExamplesByLanguage[language], `main.${parserLanguage}`);
                expect(results.length > 0).toBe(true);
            })
        }
    }
})
