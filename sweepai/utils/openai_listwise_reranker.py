"""This should take a list of snippets and rerank them"""
import re

from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message, Snippet
from sweepai.logn.cache import file_cache

# use this later
# # Contextual Request Analysis:
# <contextual_request_analysis>
# * Read each code snippet and assign each a relevance score.
# ...
# </contextual_request_analysis>

# this is roughly 66% of it's optimal performance - it's worth optimizing more in the future

example_prompt = """<example>
<user_query>
The checkout process is broken. After entering payment info, the order doesn't get created and the user sees an error page.
</user_query>

<code_snippets>
<snippet>
<snippet_path>auth.js:5-30</snippet>
<snippet_contents>
const bcrypt = require('bcryptjs');
const User = require('../models/user');
router.post('/register', async (req, res) => {
  const { email, password, name } = req.body;
  try {
    let user = await User.findOne({ email });
    if (user) {
      return res.status(400).json({ message: 'User already exists' });
    }
    user = new User({
      email,
      password,
      name
    });
    const salt = await bcrypt.genSalt(10);
    user.password = await bcrypt.hash(password, salt);
    await user.save();
    req.session.user = user;
    res.json({ message: 'Registration successful', user });
  } catch (err) {
    console.error(err);
    res.status(500).json({ message: 'Server error' });
  }  
});

router.post('/login', async (req, res) => {
  const { email, password } = req.body;

  try {
    const user = await User.findOne({ email });
    if (!user) {
      return res.status(400).json({ message: 'Invalid credentials' });
    }

    const isMatch = await bcrypt.compare(password, user.password);
    if (!isMatch) {
      return res.status(400).json({ message: 'Invalid credentials' });  
    }

    req.session.user = user;
    res.json({ message: 'Login successful', user });
  } catch (err) {
    console.error(err);
    res.status(500).json({ message: 'Server error' });
  }
});
</snippet_contents>
</snippet>

<snippet>
<snippet_path>cart_model.js:1-20</snippet>
<snippet_contents>
const mongoose = require('mongoose');
const cartSchema = new mongoose.Schema({
  user: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User',
    required: true
  },
  items: [{
    product: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'Product'
    },
    quantity: Number,
    price: Number  
  }]
}, { timestamps: true });
cartSchema.virtual('totalPrice').get(function() {
  return this.items.reduce((total, item) => total + item.price * item.quantity, 0);
});
module.exports = mongoose.model('Cart', cartSchema);
</snippet_contents>
</snippet>

<snippet>
<snippet_path>order.js:5-25</snippet>
<snippet_contents>
const Order = require('../models/order');
router.get('/', async (req, res) => {
  try {
    const orders = await Order.find({ user: req.user._id }).sort('-createdAt');
    res.json(orders);
  } catch (err) {
    console.error(err);
    res.status(500).json({ message: 'Server error' });
  }
});
router.get('/:id', async (req, res) => {
  try {
    const order = await Order.findOne({ _id: req.params.id, user: req.user._id });
    if (!order) {
      return res.status(404).json({ message: 'Order not found' });
    }
    res.json(order);
  } catch (err) {
    console.error(err);
    res.status(500).json({ message: 'Server error' });
  }  
});
</snippet_contents>
</snippet>

<snippet>
<snippet_path>checkout.js:5-30</snippet>
<snippet_contents>
router.post('/submit', async (req, res) => {
  const { cartId, paymentInfo } = req.body;
  try {
    const cart = await Cart.findById(cartId).populate('items.product');
    if (!cart) {
      return res.status(404).json({ message: 'Cart not found' });
    }
    const order = new Order({
      user: req.user._id,
      items: cart.items,
      total: cart.totalPrice,
      paymentInfo,
    });
    await order.save();
    await Cart.findByIdAndDelete(cartId);
    res.json({ message: 'Order placed successfully', orderId: order._id });
  } catch (err) {
    console.error(err);
    res.status(500).json({ message: 'Server error' });
  }
});
</snippet_contents>
</snippet>

<snippet>
<snippet_path>user_model.js:1-10</snippet>
<snippet_contents>
const mongoose = require('mongoose');
const userSchema = new mongoose.Schema({
  email: {
    type: String,
    required: true,
    unique: true
  },
  password: {
    type: String,
    required: true
  },
  name: String,
  address: String,
  phone: String,
  isAdmin: {
    type: Boolean,
    default: false  
  }
}, { timestamps: true });
module.exports = mongoose.model('User', userSchema);
</snippet_contents>
</snippet>

<snippet>
<snippet_path>index.js:10-25</snippet>
<snippet_contents>
const express = require('express');
const mongoose = require('mongoose');
const session = require('express-session');
const MongoStore = require('connect-mongo')(session);
const app = express();
mongoose.connect(process.env.MONGO_URI, {
  useNewUrlParser: true,
  useUnifiedTopology: true
});
app.use(express.json());
app.use(session({
  secret: process.env.SESSION_SECRET,
  resave: false,
  saveUninitialized: true,
  store: new MongoStore({ mongooseConnection: mongoose.connection })
}));
app.use('/auth', require('./routes/auth'));
app.use('/cart', require('./routes/cart'));  
app.use('/checkout', require('./routes/checkout'));
app.use('/orders', require('./routes/order'));
app.use('/products', require('./routes/product'));
app.use((err, req, res, next) => {
  console.error(err);
  res.status(500).json({ message: 'Server error' });
});
const PORT = process.env.PORT || 5000;
app.listen(PORT, () => console.log(`Server started on port ${PORT}`));
</snippet_contents>
</snippet>

<snippet>
<snippet_path>payment.js:3-20</snippet>
<snippet_contents>
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);
router.post('/charge', async (req, res) => {
  const { amount, token } = req.body;
  try {
    const charge = await stripe.charges.create({
      amount,
      currency: 'usd',
      source: token,
      description: 'Example charge'
    });
    res.json({ message: 'Payment successful', charge });
  } catch (err) {
    console.error(err);  
    res.status(500).json({ message: 'Payment failed' });
  }
});
</snippet_contents>
</snippet>

<snippet>
<snippet_path>product_model.js:1-12</snippet>
<snippet_contents>
const mongoose = require('mongoose');
const productSchema = new mongoose.Schema({
  name: {
    type: String,
    required: true
  },
  description: String,
  price: {
    type: Number,
    required: true,
    min: 0
  },
  category: {
    type: String,
    enum: ['electronics', 'clothing', 'home'],
    required: true  
  },
  stock: {
    type: Number,
    default: 0,
    min: 0
  }
});
module.exports = mongoose.model('Product', productSchema);
</snippet_contents>
</snippet>

<snippet>
<snippet_path>order_model.js:1-15</snippet>
<snippet_contents>
const mongoose = require('mongoose');
const orderSchema = new mongoose.Schema({
  user: { 
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User',
    required: true
  },
  items: [{
    product: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'Product'
    },
    quantity: Number,
    price: Number
  }],
  total: {
    type: Number,
    required: true
  },
  paymentInfo: {
    type: Object,
    required: true
  },
  status: {
    type: String,
    enum: ['pending', 'processing', 'shipped', 'delivered'],
    default: 'pending'
  }
}, { timestamps: true });
module.exports = mongoose.model('Order', orderSchema);
</snippet_contents>
</snippet>

<snippet>
<snippet_path>cart.js:5-20</snippet>
<snippet_contents>
router.post('/add', async (req, res) => {
  const { productId, quantity } = req.body;
  
  try {
    let cart = await Cart.findOne({ user: req.user._id });
    if (cart) {
      const itemIndex = cart.items.findIndex(item => item.product == productId);
      if (itemIndex > -1) {
        cart.items[itemIndex].quantity += quantity;
      } else {
        cart.items.push({ product: productId, quantity, price: product.price });
      }
      cart = await cart.save();
    } else {
      cart = await Cart.create({
        user: req.user._id,
        items: [{ product: productId, quantity, price: product.price }]
      });
    }
    res.json(cart);
  } catch (err) {
    console.error(err);
    res.status(500).json({ message: 'Server error' });  
  }
});
</snippet_contents>
</snippet>
</code_snippets>

<explanations>
auth.js:5-30
This code handles user registration and login. It's used to authenticate the user before checkout can occur. But since the error happens after entering payment info, authentication is likely not the problem.

cart_model.js:1-20
This defines the schema and model for shopping carts. A cart contains references to the user and product items. It also has a virtual property to calculate the total price. It's used in the checkout process but probably not the source of the bug.

order.js:5-25
This code allows fetching the logged-in user's orders. It's used after the checkout process to display order history. It doesn't come into play until after checkout is complete.

checkout.js:5-30  
This code handles the checkout process. It receives the cart ID and payment info from the request body. It finds the cart, creates a new order with the cart items and payment info, saves the order, deletes the cart, and returns the order ID. This is likely where the issue is occurring.

user_model.js:1-10
This defines the schema and model for user accounts. A user has an email, password, name, address, phone number, and admin status. The user ID is referenced by the cart and order, but the user model itself is not used in the checkout.

index.js:10-25
This is the main Express server file. It sets up MongoDB, middleware, routes, and error handling. While it's crucial for the app as a whole, it doesn't contain any checkout-specific logic.

payment.js:3-20
This code processes the actual payment by creating a Stripe charge. The payment info comes from the checkout process. If the payment fails, that could explain the checkout error, so this is important to investigate.

product_model.js:1-12
This defines the schema and model for products. A product has a name, description, price, category, and stock quantity. It's referenced by the cart and order models but is not directly used in the checkout process.

order_model.js:1-15
This defines the schema and model for orders. An order contains references to the user and product items, the total price, payment info, and status. It's important for understanding the structure of an order, but unlikely to contain bugs.

cart.js:5-20
This code handles adding items to the cart. It's used before the checkout process begins. While it's important for the overall shopping flow, it's unlikely to be directly related to a checkout bug.  
</explanations>

<ranking>
checkout.js:5-30
payment.js:3-20  
order_model.js:1-15
cart_model.js:1-20
index.js:10-25
auth.js:5-30
cart.js:5-20
order.js:5-25
user_model.js:1-10
product_model.js:1-12
</ranking>
</example>"""

reranking_prompt = f"""You are a powerful code search engine. You must order the list of code snippets from the most relevant to the least relevant to the user's query. You must order ALL TEN snippets.
First, for each code snippet, provide a brief explanation of what the code does and how it relates to the user's query.

Then, rank the snippets based on relevance. The most relevant files are the ones we need to edit to resolve the user's issue. The next most relevant snippets are dependencies - code that is crucial to read and understand while editing the other files to correctly resolve the user's issue.

Note: For each code snippet, provide an explanation of what the code does and how it fits into the overall system, even if it's not directly relevant to the user's query. The ranking should be based on relevance to the query, but all snippets should be explained.

The response format is:
<explanations>
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
</explanations>

<ranking>
first_most_relevant_snippet
second_most_relevant_snippet
third_most_relevant_snippet
fourth_most_relevant_snippet
fifth_most_relevant_snippet
sixth_most_relevant_snippet
seventh_most_relevant_snippet
eighth_most_relevant_snippet
ninth_most_relevant_snippet
tenth_most_relevant_snippet
</ranking>

Here is an example:

{example_prompt}

This example is for reference. Please provide explanations and rankings for the code snippets based on the user's query."""

user_query_prompt = """This is the user's query:
<user_query>
{user_query}
</user_query>

This is the list of ten code snippets that you must order by relevance:
<code_snippets>
{formatted_code_snippets}
</code_snippets>

Remember: The response format is:  
<explanations>
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
</explanations>

<ranking>
first_most_relevant_snippet
second_most_relevant_snippet
third_most_relevant_snippet
fourth_most_relevant_snippet
fifth_most_relevant_snippet
sixth_most_relevant_snippet
seventh_most_relevant_snippet
eighth_most_relevant_snippet
ninth_most_relevant_snippet
tenth_most_relevant_snippet
</ranking>

As a reminder, the user query is:  
<user_query>
{user_query}  
</user_query>

Provide the explanations and ranking below:"""

graph_example_prompt = """<example>
<user_query>
The checkout process is broken. After entering payment info, the order doesn't get created and the user sees an error page.
</user_query>
<code_snippets>
<snippet>
<snippet_path>checkout_utils.js:5-30</snippet>
<snippet_contents>
function processCheckout(cartId, paymentInfo) {
  return Cart.findById(cartId).populate('items.product')
    .then(cart => {
      if (!cart) {
        throw new Error('Cart not found');
      }
      const order = new Order({
        user: req.user._id,
        items: cart.items,
        total: cart.totalPrice,
        paymentInfo,
      });
      return order.save();
    })
    .then(order => {
      return Cart.findByIdAndDelete(cartId)
        .then(() => order);
    })
    .then(order => {
      return { message: 'Order placed successfully', orderId: order._id };
    })
    .catch(err => {
      console.error(err);
      throw err;
    });
}
module.exports = {
  processCheckout
};
</snippet_contents>
</snippet>
<snippet>
<snippet_path>payment_service.js:3-20</snippet>
<snippet_contents>
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);
function createPaymentCharge(amount, token) {
  return stripe.charges.create({
    amount,
    currency: 'usd',
    source: token,
    description: 'Example charge'
  })
  .then(charge => {
    return { message: 'Payment successful', charge };
  })
  .catch(err => {
    console.error(err);
    throw new Error('Payment failed');
  });
}
module.exports = {
  createPaymentCharge
};
</snippet_contents>
</snippet>
<snippet>
<snippet_path>order_model.js:1-15</snippet>
<snippet_contents>
const mongoose = require('mongoose');
const orderSchema = new mongoose.Schema({
  user: { 
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User',
    required: true
  },
  items: [{
    product: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'Product'
    },
    quantity: Number,
    price: Number
  }],
  total: {
    type: Number,
    required: true
  },
  paymentInfo: {
    type: Object,
    required: true
  },
  status: {
    type: String,
    enum: ['pending', 'processing', 'shipped', 'delivered'],
    default: 'pending'
  }
}, { timestamps: true });
module.exports = mongoose.model('Order', orderSchema);
</snippet_contents>
</snippet>
<snippet>
<snippet_path>cart_model.js:1-20</snippet>
<snippet_contents>
const mongoose = require('mongoose');
const cartSchema = new mongoose.Schema({
  user: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User',
    required: true
  },
  items: [{
    product: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'Product'
    },
    quantity: Number,
    price: Number  
  }]
}, { timestamps: true });
cartSchema.virtual('totalPrice').get(function() {
  return this.items.reduce((total, item) => total + item.price * item.quantity, 0);
});
module.exports = mongoose.model('Cart', cartSchema);
</snippet_contents>
</snippet>
<snippet>
<snippet_path>db_connect.js:1-15</snippet>
<snippet_contents>
const mongoose = require('mongoose');
function connectToDatabase(uri) {
  return mongoose.connect(uri, {
    useNewUrlParser: true,
    useUnifiedTopology: true
  })
  .then(() => {
    console.log('Connected to MongoDB');
  })
  .catch(err => {
    console.error('MongoDB connection error:', err);
    process.exit(1);
  });
}
module.exports = connectToDatabase;
</snippet_contents>
</snippet>
<snippet>
<snippet_path>auth_middleware.js:5-20</snippet>
<snippet_contents>
function requireLogin(req, res, next) {
  if (req.session && req.session.user) {
    next();
  } else {
    res.status(401).json({ message: 'Authentication required' });
  }
}
function requireAdmin(req, res, next) {
  if (req.session && req.session.user && req.session.user.isAdmin) {
    next();
  } else {
    res.status(403).json({ message: 'Admin access required' });
  }
}
module.exports = {
  requireLogin,
  requireAdmin
};
</snippet_contents>
</snippet>
<snippet>
<snippet_path>cart_utils.js:5-20</snippet>
<snippet_contents>
function addItemToCart(userId, productId, quantity) {
  return Cart.findOne({ user: userId })
    .then(cart => {
      if (cart) {
        const itemIndex = cart.items.findIndex(item => item.product == productId);
        if (itemIndex > -1) {
          cart.items[itemIndex].quantity += quantity;
        } else {
          cart.items.push({ product: productId, quantity });
        }
        return cart.save();
      } else {
        return Cart.create({
          user: userId,
          items: [{ product: productId, quantity }]
        });
      }
    });
}
module.exports = {
  addItemToCart
};
</snippet_contents>
</snippet>
<snippet>
<snippet_path>order_utils.js:5-25</snippet>
<snippet_contents>
function getOrdersByUser(userId) {
  return Order.find({ user: userId }).sort('-createdAt');
}
function getOrderById(orderId, userId) {
  return Order.findOne({ _id: orderId, user: userId });
}
function updateOrderStatus(orderId, status) {
  return Order.findByIdAndUpdate(orderId, { status }, { new: true });
}
module.exports = {
  getOrdersByUser,
  getOrderById,
  updateOrderStatus
};
</snippet_contents>
</snippet>
<snippet>
<snippet_path>user_model.js:1-10</snippet>
<snippet_contents>
const mongoose = require('mongoose');
const userSchema = new mongoose.Schema({
  email: {
    type: String,
    required: true,
    unique: true
  },
  password: {
    type: String,
    required: true
  },
  name: String,
  address: String,
  phone: String,
  isAdmin: {
    type: Boolean,
    default: false  
  }
}, { timestamps: true });
module.exports = mongoose.model('User', userSchema);
</snippet_contents>
</snippet>
<snippet>
<snippet_path>product_model.js:1-12</snippet>
<snippet_contents>
const mongoose = require('mongoose');
const productSchema = new mongoose.Schema({
  name: {
    type: String,
    required: true
  },
  description: String,
  price: {
    type: Number,
    required: true,
    min: 0
  },
  category: {
    type: String,
    enum: ['electronics', 'clothing', 'home'],
    required: true  
  },
  stock: {
    type: Number,
    default: 0,
    min: 0
  }
});
module.exports = mongoose.model('Product', productSchema);
</snippet_contents>
</snippet>
</code_snippets>
<explanations>
checkout_utils.js:5-30
This module contains the processCheckout function which handles the main checkout logic. It takes a cart ID and payment info, finds the associated cart, creates a new order from the cart data, saves the order, deletes the cart, and returns the order ID. This is the core checkout code and the most likely place for a bug causing the described issue.
payment_service.js:3-20
This module handles processing payments via the Stripe API. The createPaymentCharge function takes an amount and token, makes a request to Stripe to create a charge, and returns a success or error message. If payments are failing, this code would need to be checked and possibly debugged.  
order_model.js:1-15
This file defines the Mongoose schema and model for orders. It includes the order's user, items, total, payment info, and status. The model definition itself is unlikely to cause bugs, but it's important to understand the order data structure when debugging checkout and payment issues.
cart_model.js:1-20
This file defines the Mongoose schema and model for shopping carts. A cart contains the user, product items, quantities, and prices. It also defines a virtual property to calculate the cart's total price. The cart model is a key part of the checkout process, so it's useful to review when investigating checkout bugs.
db_connect.js:1-15
This module exports a function to connect to the MongoDB database using Mongoose. It's an essential part of the app's infrastructure, but unlikely to be related to a checkout bug unless there are issues connecting to the database.
auth_middleware.js:5-20
This module contains Express middleware functions to require authentication and admin access for certain routes. It checks for the existence of a user object in the session. While authentication and authorization are important for the app overall, this middleware is not directly involved in the checkout process.
cart_utils.js:5-20
This module exports a function to add an item to a user's cart. It finds the cart by user ID, updates the quantity if the item already exists or adds a new item. The addItemToCart function is used before starting the checkout, so while it's somewhat related, it's not a likely cause of the described checkout issue.
order_utils.js:5-25
This module provides utility functions for fetching a user's orders, getting an order by ID, and updating an order's status. These are used for displaying order history and managing orders, which happen after checkout is already completed. So while they interact with orders, they are not likely to be the source of an error during the checkout process.
user_model.js:1-10
This defines the Mongoose schema and model for user accounts. It includes fields for email, password, name, address, phone number, and admin status. The user model is used for authentication and referenced by carts and orders. But the checkout process doesn't directly interact with or modify user documents.
product_model.js:1-12
This defines the Mongoose schema and model for products, including name, description, price, category, and stock quantity. The product model is referenced by cart and order items, but the product data is not directly used or modified during the checkout flow. It's unlikely to be related to the checkout error.
</explanations>
<ranking>
checkout_utils.js:5-30
payment_service.js:3-20
order_model.js:1-15
cart_model.js:1-20
db_connect.js:1-15
order_utils.js:5-25
cart_utils.js:5-20
auth_middleware.js:5-20
user_model.js:1-10
product_model.js:1-12
</ranking>
</example>"""

graph_reranking_prompt = f"""You are a powerful code search engine. You must order the list of code snippets from the most relevant to the least relevant to the user's query. You must order ALL TEN snippets.
First, for each code snippet, provide a brief explanation of what the code does and how it relates to the user's query.
Then, rank the snippets based on probability of it being used in the final solution. The most relevant files are the ones most likely to be needed to resolve the user's issue. The next most relevant snippets are dependencies - code that is crucial to read and understand while using the other files to correctly resolve the user's issue.
Note: For each code snippet, provide an explanationof what the code does and how it fits into the overall system, even if it's not directly relevant to the user's query. The ranking should be based on probability of being used in the solution, but all snippets should be explained.
The response format is:
<explanations>
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
file_path:start_line-end_line
Explanation of what the code does, regardless of its relevance to the user's query. Provide context on how it fits into the overall system.
</explanations>
<ranking>
most_likely_to_be_used_in_solution
second_most_likely_to_be_used
third_most_likely_to_be_used
fourth_most_likely_to_be_used
fifth_most_likely_to_be_used
sixth_most_likely_to_be_used
seventh_most_likely_to_be_used
eighth_most_likely_to_be_used
ninth_most_likely_to_be_used
least_likely_to_be_used
</ranking>
Here is an example:
{example_prompt}
This example is for reference. Please provide explanations and rankings for the code snippets based on the user's query."""

prompt_mapping = {
  "default": reranking_prompt,
  "graph": graph_reranking_prompt,
}

class RerankSnippetsBot(ChatGPT):
    def rerank_list_for_query(
        self,
        user_query,
        code_snippets,
        prompt_type="default",
    ):
        self.messages = [Message(role="system", content=prompt_mapping[prompt_type])]
        # if the regex match fails return the original list
        # gpt doesn't add all snippets, we move all of the dropped snippets to the end in the original order
        # if we add duplicate snippets, we remove the duplicates
        ranking_pattern = r"<ranking>\n(.*?)\n</ranking>"
        formatted_code_snippets = self.format_code_snippets(code_snippets)
        try:
            ranking_response = self.chat_anthropic(
                content=user_query_prompt.format(
                    user_query=user_query,
                    formatted_code_snippets=formatted_code_snippets,
                ),
            )
        except Exception:
            ranking_response = self.chat(
                content=user_query_prompt.format(
                    user_query=user_query,
                    formatted_code_snippets=formatted_code_snippets,
                ),
            )
        ranking_matches = re.search(ranking_pattern, ranking_response, re.DOTALL)
        if ranking_matches is None:
            return code_snippets
        snippet_ranking = ranking_matches.group(1)
        snippet_ranking = snippet_ranking.strip()
        snippet_ranking = snippet_ranking.split("\n")
        # assert all snippet denotations are within our original list
        original_denotations = [snippet.denotation for snippet in code_snippets]
        snippet_ranking = [snippet for snippet in snippet_ranking if snippet in original_denotations]
        # dedup the list with stable ordering
        snippet_ranking = list(dict.fromkeys(snippet_ranking))
        if len(snippet_ranking) < len(code_snippets):
            # add the remaining snippets in the original order
            remaining_snippets = [snippet.denotation for snippet in code_snippets if snippet.denotation not in snippet_ranking]
            snippet_ranking.extend(remaining_snippets)
        # sort the snippets using the snippet_ranking
        ranked_snippets = sorted(code_snippets, key=lambda snippet: snippet_ranking.index(snippet.denotation))
        return ranked_snippets
    
    def format_code_snippets(self, code_snippets: list[Snippet]):
        result_str = ""
        for idx, snippet in enumerate(code_snippets):
            snippet_str = \
f'''
<snippet index="{idx + 1}">
<snippet_path>{snippet.denotation}</snippet_path>
<source>
{snippet.get_snippet(False, False)}
</source>
</snippet>
'''
            result_str += snippet_str + "\n"
        result_removed_trailing_newlines = result_str.rstrip("\n")
        return result_removed_trailing_newlines

@file_cache()
def listwise_rerank_snippets(
    user_query,
    code_snippets,
    prompt_type="default",
):
    # iterate from the bottom of the list to the top, sorting each n items then resorting with next n // 2 items
    number_to_rerank_at_once = 10
    stride = number_to_rerank_at_once // 2
    final_ordering = []
    prev_chunk = []
    for idx in range(len(code_snippets) - stride, 0, -stride):
        # if there is no prev_chunk, rerank the bottom n items
        if not prev_chunk:
            reranked_chunk = RerankSnippetsBot().rerank_list_for_query(user_query, code_snippets[idx - stride:idx + stride], prompt_type=prompt_type)
        # if there's a prev_chunk, rerank this chunk with the prev_chunk
        else:
            # chunk_to_rerank should be 5 new items and the top 5 items of the prev_chunk
            chunk_to_rerank = code_snippets[idx - stride:idx] + prev_chunk[:stride]
            reranked_chunk = RerankSnippetsBot().rerank_list_for_query(user_query, chunk_to_rerank, prompt_type=prompt_type)
        # last iteration, add all items
        if idx - stride <= 0:
            final_ordering = reranked_chunk + final_ordering
        else:
            # add the last n // 2 items to the final_ordering
            final_ordering = reranked_chunk[-stride:] + final_ordering
        prev_chunk = reranked_chunk
    return final_ordering
    
if __name__ == "__main__":
    # generate some test snippets
    def generate_snippet_obj(idx):
        snippet = Snippet(file_path="add.py", content=("\n" * (idx - 1) + "def add(a: int, b: int) -> int:\n    return a + b"), start=idx, end=idx + 1)
        return snippet
    code_snippets = [
        generate_snippet_obj(idx) for idx in range(30)
    ]
    try:
        # rank them
        final_ordering = listwise_rerank_snippets("I want to add two numbers.", code_snippets)
        print("\n".join([s.denotation for s in final_ordering]))
        # assert no duplicates or missing snippets
        assert len(set(final_ordering)) == len(final_ordering)
    except Exception as e:
        import pdb # noqa
        # pylint: disable=no-member
        pdb.post_mortem()
        raise e
