from sweepai.utils.diff import generate_new_file_from_patch

old_file = """
    <Layout
      seo={{
        title: "Terms and Conditions",
        description: `We collect several different types of information for various purposes to provide and improve our Service to you.`,
      }}>

      <div>
        <div className="px-6  privacy mt-12">
          <h1>
            Terms and Conditions for Snark AI, Inc.
          </h1>


          <h2>Introduction</h2>
          <p>These Terms and Conditions written on this webpage shall manage the user’s (“you”, “your”) use of all Activeloop/Snark AI, Inc. (“our”, “us”, “we”) services, including products, the websites at https://snark.ai, https://activeloop.ai, and https://deeplake.ai, and its subdomains (“Service”).</p>

          <p>These Terms will be applied fully and affect your use of the Service. By using the Service, you agree to accept these Terms and Conditions. You must not use the Service if you disagree with any of these Terms and Conditions.</p>
          <p>
            Minors or people below 18 years old are not allowed to use our Service.
          </p>
          <h2>Intellectual Property Rights</h2>
          <p>
            Other than the content you own, under these Terms, Activeloop/Snark AI, Inc. and/or its licensors own all intellectual property rights and materials contained on this Website. In this Agreement, Intellectual Property Rights means any and all present and future intellectual and industrial property rights, including any registered or unregistered forms of copyright, designs, patents, trademarks, service marks, domain names, goodwill, and any commercial information. Intellectual Property Rights also include any application or right to apply for registrations of any of these rights, any rights protected or recognized under any laws throughout the world, related to these rights, and anything copied or derived from such property or rights.
          </p>

          <p>You are granted a limited, non-exclusive, non-transferable, non-assignable, and non-sublicensable license only for purposes of viewing the material contained on this Website.</p>
          <h2>Restrictions</h2>
          <p>You are specifically restricted from all of the following:</p>
          <ul>
            <li>selling, sublicensing, and/or otherwise commercializing any Service material;</li>
            <li>using the Service in any way that is or may be damaging to Activeloop/Snark AI;</li>
            <li>using this Service in any way that impacts user access to this Service;</li>
            <li>using this Service contrary to applicable laws and regulations, the Privacy Policy, or in any way may cause harm to the Service, or to any person or business entity;</li>
            <li>engaging in any data mining, data harvesting, data extracting, or any other similar activity in relation to this Service;</li>
            <li>using this Service to engage in any advertising or marketing unless permitted to in writing by us;</li>
            <li>uploading illegal or age-restricted content; and</li>
            <li>uploading content you do not have legal authority to upload, for example, but not limited to, copyrighted content.</li>
          </ul>


          <p>
            Certain areas of this Website are restricted from being accessed by you and Activeloop/Snark AI, Inc. may further restrict access by you to any areas of this Website, at any time, in absolute discretion.
            Confidentiality
            To provide the Services to you, you may upload Confidential information. In so doing, you acknowledge and agree that:
            (a) You have the right to possess and upload the data; and
            (b) Uploaded data are subject to the terms of any relevant Confidentiality Notice provided to your users by you or a third-partry through the Services.
          </p>

          <h2>Your Content</h2>
          <p>
            In these Terms and Conditions, "Your Content" shall mean any audio, video text, images, or other material you choose to display on this Website. By displaying Your Content, you grant Activeloop/Snark AI, Inc. a non-exclusive, worldwide, irrevocable, sublicensable license to use, reproduce, adapt, publish, translate, and distribute it in any and all media.
            Your Content must be your own and must not infringe upon any third-party’s rights. Activeloop/Snark AI, Inc. reserves the right to remove any of Your Content from the Service at any time without notice if We discover a breach of these Terms.
          </p>
          <h2>Data Retention/Disaster Recovery</h2>
          <p>
            Activeloop/Snark AI, Inc. will retain backup copies of Your Content made in the ordinary course of business by Activeloop/Snark AI, Inc. for the purpose of enabling appropriate data retention and disaster recovery practices. Despite any other term in this Agreement,  Activeloop/Snark AI, Inc. will retain these backups for a period of up to thirty (30) days from the time that each backup copy is generated. Thereafter, Customer agrees and acknowledges that Your Content may be irretrievably deleted from backups after this time.
          </p>
          <h2>No Warranties</h2>
          <p>
            This Service is provided "as is" with all fault, and Activeloop/Snark AI, Inc. expresses no representations or warranties of any kind related to the Service or the materials contained in the Service. Also, nothing contained in this Service shall be interpreted as advice.
          </p>
          <h2>Limitation of Liability</h2>
          <p>
            In no event shall Activeloop/Snark AI, Inc., nor any of its officers, directors, or employees, be held liable for anything arising out of or in any way connected to your use of this Service. Activeloop/Snark AI, Inc., including its officers, directors, and employees shall not be held liable for any indirect, consequential, or special liability arising out of or in any way related to your use of this Website. Activeloop/Snark AI, Inc. is not liable for the contents of any uploaded data.
          </p>
          <h2>Indemnification</h2>
          <p>
            You hereby indemnify to the fullest extent Activeloop/Snark AI, Inc. from and against all liabilities, costs, demands, causes of action, damages, and expenses arising in any way related to your breach of any of the provisions of these Terms.
          </p>
          <h2>Severability</h2>
          <p>
            If any provision of these Terms is found to be invalid under any applicable law, such provisions shall be deleted without affecting the remaining provisions herein.
          </p>
          <h2>Variation of Terms</h2>
          <p>
            Activeloop/Snark AI, Inc. is permitted to revise these Terms at any time as it sees fit and by using the Service, you are expected to review these Terms on a regular basis.
          </p>
          <h2>Assignment</h2>
          <p>
            Activeloop/Snark AI, Inc. is allowed to assign, transfer, and subcontract its rights and/or obligations under these Terms without any notification. However, you are not allowed to assign, transfer, or subcontract any of your rights and/or obligations under these Terms.
          </p>
          <h2>Entire Agreement</h2>
          <p>
            These Terms constitute the entire agreement between Activeloop/Snark AI, Inc. and you in relation to your use of this Service and supersede all prior agreements and understandings.
          </p>
          <h2>Governing Law & Jurisdiction</h2>
          <p>
            These Terms will be governed by and interpreted in accordance with the laws of the State of California and you submit to the non-exclusive jurisdiction of the state and federal courts located in the County of Santa Clara for the resolution of any disputes.
          </p>


          <div className="mt-5 text-xs text-gray-400">
            <a href="https://termsandcondiitionssample.com/">
              These terms and conditions have been generated at
              TermsAndConditionsSample.com
            </a>
          </div>
        </div>
      </div>
    </Layout>
  )
}
"""

code_replaces = """
<<<< ORIGINAL
          <h2>Governing Law & Jurisdiction</h2>
          <p>
            These Terms will be governed by and interpreted in accordance with the laws of the State of California and you submit to the non-exclusive jurisdiction of the state and federal courts located in the County of Santa Clara for the resolution of any disputes.
          </p>


          <div className="mt-5 text-xs text-gray-400">
            <a href="https://termsandcondiitionssample.com/">
              These terms and conditions have been generated at
              TermsAndConditionsSample.com
            </a>
          </div>
        </div>
      </div>
    </Layout>
  )
}

</old_file>
====
          <h2>Governing Law & Jurisdiction</h2>
          <p>
            These Terms will be governed by and interpreted in accordance with the laws of the State of California and you submit to the non-exclusive jurisdiction of the state and federal courts located in the County of Santa Clara for the resolution of any disputes.
          </p>
        </div>
      </div>
    </Layout>
    <div>
      <div className="px-6  privacy mt-12">
        <h1>
          Terms and Conditions for Snark AI, Inc.
        </h1>


        <h2>Introduction</h2>
        <p>These Terms and Conditions written on this webpage shall manage the user’s (“you”, “your”) use of all Activeloop/Snark AI, Inc. (“our”, “us”, “we”) services, including products, the websites at https://snark.ai, https://activeloop.ai, and https://deeplake.ai, and its subdomains (“Service”).</p>

        <p>These Terms will be applied fully and affect your use of the Service. By using the Service, you agree to accept these Terms and Conditions. You must not use the Service if you disagree with any of these Terms and Conditions.</p>
        <p>
          Minors or people below 18 years old are not allowed to use our Service.
        </p>
        <h2>Intellectual Property Rights</h2>
        <p>
          Other than the content you own, under these Terms, Activeloop/Snark AI, Inc. and/or its licensors own all intellectual property rights and materials contained on this Website. In this Agreement, Intellectual Property Rights means any and all present and future intellectual and industrial property rights, including any registered or unregistered forms of copyright, designs, patents, trademarks, service marks, domain names, goodwill, and any commercial information. Intellectual Property Rights also include any application or right to apply for registrations of any of these rights, any rights protected or recognized under any laws throughout the world, related to these rights, and anything copied or derived from such property or rights.
        </p>

        <p>You are granted a limited, non-exclusive, non-transferable, non-assignable, and non-sublicensable license only for purposes of viewing the material contained on this Website.</p>
        <h2>Restrictions</h2>
        <p>You are specifically restricted from all of the following:</p>
        <ul>
          <li>selling, sublicensing, and/or otherwise commercializing any Service material;</li>
          <li>using the Service in any way that is or may be damaging to Activeloop/Snark AI;</li>
          <li>using this Service in any way that impacts user access to this Service;</li>
          <li>using this Service contrary to applicable laws and regulations, the Privacy Policy, or in any way may cause harm to the Service, or to any person or business entity;</li>
          <li>engaging in any data mining, data harvesting, data extracting, or any other similar activity in relation to this Service;</li>
          <li>using this Service to engage in any advertising or marketing unless permitted to in writing by us;</li>
          <li>uploading illegal or age-restricted content; and</li>
          <li>uploading content you do not have legal authority to upload, for example, but not limited to, copyrighted content.</li>
        </ul>


        <p>
          Certain areas of this Website are restricted from being accessed by you and Activeloop/Snark AI, Inc. may further restrict access by you to any areas of this Website, at any time, in absolute discretion.
          Confidentiality
          To provide the Services to you, you may upload Confidential information. In so doing, you acknowledge and agree that:
          (a) You have the right to possess and upload the data; and
          (b) Uploaded data are subject to the terms of any relevant Confidentiality Notice provided to your users by you or a third-partry through the Services.
        </p>

        <h2>Your Content</h2>
        <p>
          In these Terms and Conditions, "Your Content" shall mean any audio, video text, images, or other material you choose to display on this Website. By displaying Your Content, you grant Activeloop/Snark AI, Inc. a non-exclusive, worldwide, irrevocable, sublicensable license to use, reproduce, adapt, publish, translate, and distribute it in any and all media.
          Your Content must be your own and must not infringe upon any third-party’s rights. Activeloop/Snark AI, Inc. reserves the right to remove any of Your Content from the Service at any time without notice if We discover a breach of these Terms.
        </p>
        <h2>Data Retention/Disaster Recovery</h2>
        <p>
          Activeloop/Snark AI, Inc. will retain backup copies of Your Content made in the ordinary course of business by Activeloop/Snark AI, Inc. for the purpose of enabling appropriate data retention and disaster recovery practices. Despite any other term in this Agreement,  Activeloop/Snark AI, Inc. will retain these backups for a period of up to thirty (30) days from the time that each backup copy is generated. Thereafter, Customer agrees and acknowledges that Your Content may be irretrievably deleted from backups after this time.
        </p>
        <h2>No Warranties</h2>
        <p>
          This Service is provided "as is" with all fault, and Activeloop/Snark AI, Inc. expresses no representations or warranties of any kind related to the Service or the materials contained in the Service. Also, nothing contained in this Service shall be interpreted as advice.
        </p>
        <h2>Limitation of Liability</h2>
        <p>
          In no event shall Activeloop/Snark AI, Inc., nor any of its officers, directors, or employees, be held liable for anything arising out of or in any way connected to your use of this Service. Activeloop/Snark AI, Inc., including its officers, directors, and employees shall not be held liable for any indirect, consequential, or special liability arising out of or in any way related to your use of this Website. Activeloop/Snark AI, Inc. is not liable for the contents of any uploaded data.
        </p>
        <h2>Indemnification</h2>
        <p>
          You hereby indemnify to the fullest extent Activeloop/Snark AI, Inc. from and against all liabilities, costs, demands, causes of action, damages, and expenses arising in any way related to your breach of any of the provisions of these Terms.
        </p>
        <h2>Severability</h2>
        <p>
          If any provision of these Terms is found to be invalid under any applicable law, such provisions shall be deleted without affecting the remaining provisions herein.
        </p>
        <h2>Variation of Terms</h2>
        <p>
          Activeloop/Snark AI, Inc. is permitted to revise these Terms at any time as it sees fit and by using the Service, you are expected to review these Terms on a regular basis.
        </p>
        <h2>Assignment</h2>
        <p>
          Activeloop/Snark AI, Inc. is allowed to assign, transfer, and subcontract its rights and/or obligations under these Terms without any notification. However, you are not allowed to assign, transfer, or subcontract any of your rights and/or obligations under these Terms.
        </p>
        <h2>Entire Agreement</h2>
        <p>
          These Terms constitute the entire agreement between Activeloop/Snark AI, Inc. and you in relation to your use of this Service and supersede all prior agreements and understandings.
        </p>
        <h2>Governing Law & Jurisdiction</h2>
        <p>
          These Terms will be governed by and interpreted in accordance with the laws of the State of California and you submit to the non-exclusive jurisdiction of the state and federal courts located in the County of Santa Clara for the resolution of any disputes.
        </p>
      </div>
    </div>
  </Layout>
  <div>
    <div className="px-6  privacy mt-12">
      <h1>
        Terms and Conditions for Snark AI, Inc.
      </h1>


      <h2>Introduction</h2>
      <p>These Terms and Conditions written on this webpage shall manage the user’s (“you”, “your”) use of all Activeloop/Snark AI, Inc. (“our”, “us”, “we”) services, including products, the websites at https://snark.ai, https://activeloop.ai, and https://deeplake.ai, and its subdomains (“Service”).</p>

      <p>These Terms will be applied fully and affect your use of the Service. By using the Service, you agree to accept these Terms and Conditions. You must not use the Service if you disagree with any of these Terms and Conditions.</p>
      <p>
        Minors or people below 18 years old are not allowed to use our Service.
      </p>
      <h2>Intellectual Property Rights</h2>
      <p>
        Other than the content you own, under these Terms, Activeloop/Snark AI, Inc. and/or its licensors own all intellectual property rights and materials contained on this Website. In this Agreement, Intellectual Property Rights means any and all present and future intellectual and industrial property rights, including any registered or unregistered forms of copyright, designs, patents, trademarks, service marks, domain names, goodwill, and any commercial information. Intellectual Property Rights also include any application or right to apply for registrations of any of these rights, any rights protected or recognized under any laws throughout the world, related to these rights, and anything copied or derived from such property or rights.
      </p>

      <p>You are granted a limited, non-exclusive, non-transferable, non-assignable, and non-sublicensable license only for purposes of viewing the material contained on this Website.</p>
      <h2>Restrictions</h2>
      <p>You are specifically restricted from all of the following:</p>
      <ul>
        <li>selling, sublicensing, and/or otherwise commercializing any Service material;</li>
        <li>using the Service in any way that is or may be damaging to Activeloop/Snark AI;</li>
        <li>using this Service in any way that impacts user access to this Service;</li>
        <li>using this Service contrary to applicable laws and regulations, the Privacy Policy, or in any way may cause harm to the Service, or to any person or business entity;</li>
        <li>engaging in any data mining, data harvesting, data extracting, or any other similar activity in relation to this Service;</li>
        <li>using this Service to engage in any advertising or marketing unless permitted to in writing by us;</li>
        <li>uploading illegal or age-restricted content; and</li>
        <li>uploading content you do not have legal authority to upload, for example, but not limited to, copyrighted content.</li>
      </ul>


      <p>
        Certain areas of this Website are restricted from being accessed by you and Activeloop/Snark AI, Inc. may further restrict access by you to any areas of this Website, at any time, in absolute discretion.
        Confidentiality
        To provide the Services to you, you may upload Confidential information. In so doing, you acknowledge and agree that:
        (a) You have the right to possess and upload the data; and
        (b) Uploaded data are subject to the terms of any relevant Confidentiality Notice provided to your users by you or a third-partry through the Services.
      </p>

      <h2>Your Content</h2>
      <p>
        In these Terms and Conditions, "Your Content" shall mean any audio, video text, images, or other material you choose to display on this Website. By displaying Your Content, you grant Activeloop/Snark AI, Inc. a non-exclusive, worldwide, irrevocable, sublicensable license to use, reproduce, adapt, publish, translate, and distribute it in any and all media.
        Your Content must be your own and must not infringe upon any third-party’s rights. Activeloop/Snark AI, Inc. reserves the right to remove any of Your Content from the Service at any time without notice if We discover a breach of these Terms.
      </p>
      <h2>Data Retention/Disaster Recovery</h2>
      <p>
        Activeloop/Snark AI, Inc. will retain backup copies of Your Content made in the ordinary course of business by Activeloop/Snark AI, Inc. for the purpose of enabling appropriate data retention and disaster recovery practices. Despite any other term in this Agreement,  Activeloop/Snark AI, Inc. will retain these backups for a period of up to thirty (30) days from the time that each backup copy is generated. Thereafter, Customer agrees and acknowledges that Your Content may be irretrievably deleted from backups after this time.
      </p>
      <h2>No Warranties</h2>
      <p>
        This Service is provided "as is" with all fault, and Activeloop/Snark AI, Inc. expresses no representations or warranties of any kind related to the Service or the materials contained in the Service. Also, nothing contained in this Service shall be interpreted as advice.
      </p>
      <h2>Limitation of Liability</h2>
      <p>
        In no event shall Activeloop/Snark AI, Inc., nor any of its officers, directors, or employees, be held liable for anything arising out of or in any way connected to your use of this Service. Activeloop/Snark AI, Inc., including its officers, directors, and employees shall not be held liable for any indirect, consequential, or special liability arising out of or in any way related to your use of this Website. Activeloop/Snark AI, Inc. is not liable for the contents of any uploaded data.
      </p>
      <h2>Indemnification</h2>
      <p>
        You hereby indemnify to the fullest extent Activeloop/Snark AI, Inc. from and against all liabilities, costs, demands, causes of action, damages, and expenses arising in any way related to your breach of any of the provisions of these Terms.
      </p>
      <h2>Severability</h2>
      <p>
        If any provision of these Terms is found to be invalid under any applicable law, such provisions shall be deleted without affecting the remaining provisions herein.
      </p>
      <h2>Variation of Terms</h2>
      <p>
        Activeloop/Snark AI, Inc. is permitted to revise these Terms at any time as it sees fit and by using the Service, you are expected to review these Terms on a regular basis.
      </p>
      <h2>Assignment</h2>
      <p>
        Activeloop/Snark AI, Inc. is allowed to assign, transfer, and subcontract its rights and/or obligations under these Terms without any notification. However, you are not allowed to assign, transfer, or subcontract any of your rights and/or obligations under these Terms.
      </p>
      <h2>Entire Agreement</h2>
      <p>
        These Terms constitute the entire agreement between Activeloop/Snark AI, Inc. and you in relation to your use of this Service and supersede all prior agreements and understandings.
      </p>
      <h2>Governing Law & Jurisdiction</h2>
      <p>
        These Terms will be governed by and interpreted in accordance with the laws of the State of California and you submit to the non-exclusive jurisdiction of the state and federal courts located in the County of Santa Clara for the resolution of any disputes.
      </p>
    </div>
  </div>
</Layout>
<div>
  <div className="px-6  privacy mt-12">
    <h1>
      Terms and Conditions for Snark AI, Inc.
    </h1>


    <h2>Introduction</h2>
    <p>These Terms and Conditions written on this webpage shall manage the user’s (“you”, “your”) use of all Activeloop/Snark AI, Inc. (“our”, “us”, “we”) services, including products, the websites at https://snark.ai, https://activeloop.ai, and https://deeplake.ai, and its subdomains (“Service”).</p>

    <p>These Terms will be applied fully and affect your use of the Service. By using the Service, you agree to accept these Terms and Conditions. You must not use the Service if you disagree with any of these Terms and Conditions.</p>
    <p>
      Minors or people below 18 years old are not allowed to use our Service.
    </p>
    <h2>Intellectual Property Rights</h2>
    <p>
      Other than the content you own, under these Terms, Activeloop/Snark AI, Inc. and/or its licensors own all intellectual property rights and materials contained on this Website. In this Agreement, Intellectual Property Rights means any and all present and future intellectual and industrial property rights, including any registered or unregistered forms of copyright, designs, patents, trademarks, service marks, domain names, goodwill, and any commercial information. Intellectual Property Rights also include any application or right to apply for registrations of any of these rights, any rights protected or recognized under any laws throughout the world, related to these rights, and anything copied or derived from such property or rights.
    </p>

    <p>You are granted a limited, non-exclusive, non-transferable, non-assignable, and non-sublicensable license only for purposes of viewing the material contained on this Website.</p>
    <h2>Restrictions</h2>
    <p>You are specifically restricted from all of the following:</p>
    <ul>
      <li>selling, sublicensing, and/or otherwise commercializing any Service material;</li>
      <li>using the Service in any way that is or may be damaging to Activeloop/Snark AI;</li>
      <li>using this Service in any way that impacts user access to this Service;</li>
      <li>using this Service contrary to applicable laws and regulations, the Privacy Policy, or in any way may cause harm to the Service, or to any person or business entity;</li>
      <li>engaging in any data mining, data harvesting, data extracting, or any other similar activity in relation to this Service;</li>
      <li>using this Service to engage in any advertising or marketing unless permitted to in writing by us;</li>
      <li>uploading illegal or age-restricted content; and</li>
      <li>uploading content you do not have legal authority to upload, for example, but not limited to, copyrighted content.</li>
    </ul>


    <p>
      Certain areas of this Website are restricted from being accessed by you and Activeloop/Snark AI, Inc. may further restrict access by you to any areas of this Website, at any time, in absolute discretion.
      Confidentiality
      To provide the Services to you, you may upload Confidential information. In so doing, you acknowledge and agree that:
      (a) You have the right to possess and upload the data; and
      (b) Uploaded data are subject to the terms of any relevant Confidentiality Notice provided to your users by you or a third-partry through the Services.
    </p>

    <h2>Your Content</h2>
    <p>
      In these Terms and Conditions, "Your Content" shall mean any audio, video text, images, or other material you choose to display on this Website. By displaying Your Content, you grant Activeloop/Snark AI, Inc. a non-exclusive, worldwide, irrevocable, sublicensable license to use, reproduce, adapt, publish, translate, and distribute it in any and all media.
      Your Content must be your own and must not infringe upon any third-party’s rights. Activeloop/Snark AI, Inc. reserves the right to remove any of Your Content from the Service at any time without notice if We discover a breach of these Terms.
    </p>
    <h2>Data Retention/Disaster Recovery</h2>
    <p>
      Activeloop/Snark AI, Inc. will retain backup copies of Your Content made in the ordinary course of business by Activeloop/Snark AI, Inc. for the purpose of enabling appropriate data retention and disaster recovery practices. Despite any other term in this Agreement,  Activeloop/Snark AI, Inc. will retain these backups for a period of up to thirty (30) days from the time that each backup copy is generated. Thereafter, Customer agrees and acknowledges that Your Content may be irretrievably deleted from backups after this time.
    </p>
    <h2>No Warranties</h2>
    <p>
      This Service is provided "as is" with all fault, and Activeloop/Snark AI, Inc. expresses no representations or warranties of any kind related to the Service or the materials contained in the Service. Also, nothing contained in this Service shall be interpreted as advice.
    </p>
    <h2>Limitation of Liability</h2>
    <p>
      In no event shall Activeloop/Snark AI, Inc., nor any of its officers, directors, or employees, be held liable for anything arising out of or in any way connected to your use of this Service. Activeloop/Snark AI, Inc., including its officers, directors, and employees shall not be held liable for any indirect, consequential, or special liability arising out of or in any way related to your use of this Website. Activeloop/Snark AI, Inc. is not liable for the contents of any uploaded data.
    </p>
    <h2>Indemnification</h2>
    <p>
      You hereby indemnify to the fullest extent Activeloop/Snark AI, Inc. from and against all liabilities, costs, demands, causes of action, damages, and expenses arising in any way related to your breach of any of the provisions of these Terms.
    </p>
    <h2>Severability</h2>
    <p>
      If any provision of these Terms is found to be invalid under any applicable law, such provisions shall be deleted without affecting the remaining provisions herein.
    </p>
    <h2>Variation of Terms</h2>
    <p>
      Activeloop/Snark AI, Inc. is permitted to revise these Terms at any time as it sees fit and by using the Service, you are expected to review these Terms on a regular basis.
    </p>
    <h2>Assignment</h2>
    <p>
      Activeloop/Snark AI, Inc. is allowed to assign, transfer, and subcontract its rights and/or obligations under these Terms without any notification. However, you are not allowed to assign, transfer, or subcontract any of your rights and/or obligations under these Terms.
    </p>
    <h2>Entire Agreement</h2>
    <p>
      These Terms constitute the entire agreement between Activeloop/Snark AI, Inc. and you in relation to your use of this Service and supersede all prior agreements and understandings.
    </p>
    <h2>Governing Law & Jurisdiction</h2>
    <p>
      These Terms will be governed by and interpreted in accordance with the laws of the State of California and you submit to the non-exclusive jurisdiction of the state and federal courts located in the County of Santa Clara for the resolution of any disputes.
    </p>
  </div>
</div>
</Layout>
```
"""

if __name__ == "__main__":
    print(generate_new_file_from_patch(code_replaces, old_file)[0])
