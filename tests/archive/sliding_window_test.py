from sweepai.utils.diff import generate_new_file_from_patch

old_file = """
    defmodule incorrect2 do
      this is bad2
      this is very bad2
    end

    defmodule Test do
      print("hey")
      print("not worth")

      if this breaks then
        i'm sad
      end
    end

    defmodule incorrect do
      this is bad
      this is very bad
    end"""

message = """<<<< ORIGINAL
defmodule Test do
  ...
end
====
defmodule Test do
  ...

  describe "something" do
    it "does something" do
        assert true
  end
end
>>>> UPDATED"""

print(generate_new_file_from_patch(message, old_file))
