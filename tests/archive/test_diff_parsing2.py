from sweepai.utils.diff import generate_new_file_from_patch

old_file = r"""
import ExternalLinkWithText from "./ExternalLinkWithText";
const demo = require("../assets/demo.mp4");

export default class CallToAction extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      spin: false,
    };
  }
  // const canvas = document.getElementById('canvas3d');
  // const app = new Application(canvas);
  // app.load('https://prod.spline.design/jzV1MbbHCyCmMG7u/scene.splinecode');
  return (
    <Container maxW={"5xl"}>
      <Stack
"""

old_file = r"""
        ticket_count = (
            result_list[0].get(tracking_date, 0) if len(result_list) > 0 else 0
        )
        logger.info(f"Ticket Count for {username} {ticket_count}")
        return ticket_count

    def is_paying_user(self):
        if self.ticket_collection is None:
            logger.error("Ticket Collection Does Not Exist")
            return False
        username = self.data["username"]
        result = self.ticket_collection.find_one({"username": username})
        return result.get("is_paying_user", False) if result else False

    def is_trial_user(self):
        if self.ticket_collection is None:
            logger.error("Ticket Collection Does Not Exist")
            return False
        username = self.data["username"]
        result = self.ticket_collection.find_one({"username": username})
        return result.get("is_trial_user", False) if result else False

    def use_faster_model(self, g):
        if self.ticket_collection is None:
            logger.error("Ticket Collection Does Not Exist")
            return True
        if self.is_paying_user():
            return self.get_ticket_count() >= 500
        if self.is_trial_user():
            return self.get_ticket_count() >= 15

        try:
            loc_user = g.get_user(self.data["username"]).location
            loc = Nominatim(user_agent="location_checker").geocode(
                loc_user, exactly_one=True
            )
            g = False
            for c in SUPPORT_COUNTRY:
                if c.lower() in loc.raw.get("display_name").lower():
                    g = True
                    break
            if not g:
                logger.print("G EXCEPTION", loc_user)
                return (
                    self.get_ticket_count() >= 5
                    or self.get_ticket_count(use_date=True) >= 1
                )
        except SystemExit:
            raise SystemExit
"""

# code_replaces = """
# ```
# <<<< ORIGINAL
# export default class CallToAction extends React.Component {
#   constructor(props) {
#     super(props);
#     this.state = {
#       spin: false,
#     };
#   }
#   return (
#     <Container maxW={"5xl"}>
# ====
# export default class CallToAction extends React.Component {
#   constructor(props) {
#     super(props);
#     this.state = {
#       spin: false,
#     };
#   }
#   render() {
#     return (
#       <Container maxW={"5xl"}>
# >>>> UPDATED
# ```
# """

code_replaces = """
<<<< ORIGINAL
def use_faster_model(self, g):
    if self.ticket_collection is None:
        logger.error("Ticket Collection Does Not Exist")
        return True
    if self.is_paying_user():
        return self.get_ticket_count() >= 500
    if self.is_trial_user():
        return self.get_ticket_count() >= 15
====
def use_faster_model(self, g):
    if self.ticket_collection is None:
        logger.error("Ticket Collection Does Not Exist")
        return True
    if self.is_paying_user():
        return self.get_ticket_count() >= 500
    if self.is_consumer_tier():
        return self.get_ticket_count() >= 20

    try:
        loc_user = g.get_user(self.data["username"]).location
        loc = Nominatim(user_agent="location_checker").geocode(
            loc_user, exactly_one=True
        )
        g = False
        for c in SUPPORT_COUNTRY:
            if c.lower() in loc.raw.get("display_name").lower():
                g = True
                break
        if not g:
            logger.print("G EXCEPTION", loc_user)
            return (
                self.get_ticket_count() >= 5
                or self.get_ticket_count(use_date=True) >= 1
            )
    except SystemExit:
        raise SystemExit
>>>> UPDATED
"""

if __name__ == "__main__":
    print(generate_new_file_from_patch(code_replaces, old_file)[0])
    # generate_new_file_from_patch(code_replaces, old_file)[0]
