# Black USB clip-on reading light

CJ product: `1616320554628296704` (`CJJT1666548`).
Selected variant: `1616320554695405569`, `Black-USB-1PC`.
Selected SKU: `CJJT166654802BY`. One black light, not a multipack.
Retail: USD 16.99 with standard US shipping included; origin CN.

The owner authorized direct publication without a physical sample. The English
and Spanish listing describes the supplier's USB charging connector, adjustable
head, clip and ABS construction. Dimensions are attributed to the supplier.
No battery runtime, brightness levels, health or certification claims are made.
Carrier transit is distinguished from sourcing/preparation time.

The original black-variant photograph was visually reviewed and copied without
editing to `assets/products/usb-clip-reading-light/main.jpg`:
https://cf.cjdropshipping.com/52829598-a4a8-4e9a-bce8-8880d08ada8b.jpg

The supplier's white, pink, yellow and mixed-colour photos are omitted from
the customer listing. Only black is enabled for purchase.

After a normal GitHub Actions deploy, publish with:

```sh
gh workflow run run-script.yml -f script=publish_usb_reading_light.py -f args=--publish
```

The publisher rechecks exact PID/VID/SKU, positive China inventory, unit cost
at most USD 4.10 and freight at most USD 6.50 for US ZIPs 10001 and 90001.
It atomically updates only this product and variant, preserving IDs on reruns.
Supplier/slug collisions and duplicate supplier products are rejected. The
private validation report records the latest stock, costs and activation.
No customer order, sample order, payment or social post is created.

`--assets` imports original supplier photos for review without activating sales;
unusable additional photos are skipped and a usable selected-variant photo is
required. `--draft` prepares an inactive listing and refuses to hide an active
one. No arguments prints the intended SKU and retail only.
