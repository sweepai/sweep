echo "Get an OpenAI key from https://platform.openai.com/api-keys and paste it below."
read -p "OpenAI API key: " OPENAI_API_KEY

cd ~/
# git clone https://github.com/sweepai/sweep
cd sweep/platform
echo "Storing OpenAI API key in .env.local..."
# echo "OPENAI_API_KEY=$OPENAI_API_KEY" > .env.local
# npm i
# npm run build

echo ""
echo "To run the assistant, run the following command:"
echo ""
echo "npm start --prefix ~/sweep/platform"
echo ""

echo "To alias it to sweep, run the following command:"
echo ""
echo 'echo "alias sweep='npm start --prefix ~/sweep/platform'" >> ~/.zshrc'
