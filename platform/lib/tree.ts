import Parser, { SyntaxNode, Tree } from 'tree-sitter';
// @ts-ignore
import JavaScript from 'tree-sitter-javascript';
// @ts-ignore
import { tsx, typescript } from 'tree-sitter-typescript';
// @ts-ignore
import Python from 'tree-sitter-python';
// @ts-ignore
import Rust from 'tree-sitter-rust';
// @ts-ignore
import HTML from 'tree-sitter-html';

const languageMap: {[key in string]: string} = {
    "js": JavaScript,
    "jsx": JavaScript,
    "ts": typescript,
    "tsx": tsx,
    "py": Python,
    "rust": Rust,
    "html": HTML,
}

const parseCode = (sourceCode: string, language: any) => {
    const parser = new Parser();
    parser.setLanguage(language);
    return parser.parse(sourceCode);
}

const checkTree = (tree: Tree): string => {
    // Return the first error found in the tree
    var nextLevel = [tree.rootNode];
    var deepestError: SyntaxNode | null = null;
    while (nextLevel.length > 0) {
        const currentLevel = nextLevel;
        nextLevel = [];
        for (const node of currentLevel) {
            if (node.hasError()) {
                deepestError = node;
            }
            nextLevel.push(...node.children);
        }
    }
    if (deepestError) {
        const type = deepestError.type === "ERROR" ? "Syntax Error" : "Missing Node";
        return `${type} between ${deepestError.startPosition.row}:${deepestError.startPosition.column} - ${deepestError.endPosition.row}:${deepestError.endPosition.column}`;
    }
    return ""
}

const checkCode = (sourceCode: string, filePath: string) => {
    const ext = filePath.split('.').pop() || '';
    const language = languageMap[ext];
    if (!language) {
        return "";
    }
    const tree = parseCode(sourceCode, language);
    return checkTree(tree);
}

export { parseCode, checkTree, checkCode };
