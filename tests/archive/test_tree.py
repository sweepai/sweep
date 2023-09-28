tree_str = """\
.github/...
.gitignore
.vscode/...
README.md
package.json
public/
  KEVIN.jpeg
  Luke_Picture.jpeg
  android-chrome-192x192.png
  favicon.ico
  favicon.old.ico
  final-sweep-wizard_128x128.png
  final-sweep-wizard_16x16.png
  final-sweep-wizard_256x256.png
  final-sweep-wizard_32x32.png
  final-sweep-wizard_48x48.png
  final-sweep-wizard_64x64.png
  index.html
  logo192.png
  logo512.png
  manifest.json
  og_image (copy).png
  og_image.old.png
  og_image.png
  robots.txt
  sla.pdf
  wz_pfp.png
src/
  App.test.tsx
  App.tsx
  ColorModeSwitcher.tsx
  assets/...
  src/components/
    AboutUs.tsx
    Banner.tsx
    CallToAction.tsx
    Conclusion.tsx
    Examples.tsx
    ExternalLinkWithText.tsx
    Features.tsx
    Footer.tsx
    Navbar.tsx
    PricingModal.tsx
    PricingPage.tsx
    Testimonials.tsx
    User.tsx
    Users.tsx
  index.tsx
  logo.svg
  react-app-env.d.ts
  reportWebVitals.ts
  serviceWorker.ts
  setupTests.ts
  test-utils.tsx
sweep.yaml
tsconfig.json
yarn.lock"""

from sweepai.utils.tree_utils import DirectoryTree

tree = DirectoryTree()
tree.parse(tree_str)
# tree.remove_multiple(["sweepai/", "tests/", "docs/"])
# print(tree)
# print("\n\n")
serialized_list = [
    'src/components/',
    'src/components/PricingPage.tsx',
    'package.json',
    'yarn.lock'
]
tree.remove_all_not_included(serialized_list)
print()
print(tree)
tree.expand_directory(["src/"])
print()
print(tree)