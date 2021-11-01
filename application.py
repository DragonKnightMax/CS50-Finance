import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # query rows that match the user id
    stocks = db.execute("SELECT symbol, name, SUM(shares) AS holdings FROM history WHERE user_id = :user_id GROUP BY symbol", user_id=session["user_id"])

    portfolio = []
    subtotal = 0
    for stock in stocks:

        # calculate the total holdings of each stock
        stock_info = lookup(stock["symbol"])
        temp = {
            "symbol": stock["symbol"],
            "name": stock["name"],
            "shares": stock["holdings"],
            "price": usd(stock_info["price"]),
            "total": usd(stock_info["price"] * stock["holdings"])
        }

        # calculate subtotal of assets
        subtotal += stock_info["price"] * stock["holdings"]

        # create a row for each stock
        portfolio.append(temp)

    # query for user current cash balance in account
    cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])
    cash = cash[0]["cash"]

    subtotal += cash

    return render_template("index.html", portfolio=portfolio, cash=usd(cash), subtotal=usd(subtotal))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        # ensure symbol was.submitted
        if not request.form.get("symbol"):
            return apology("must provide a symbol", 403)

        # ensure no of shares was submitted
        elif not request.form.get("shares"):
            return apology("must provide no. of shares", 403)

        elif not request.form.get("shares").isdigit():
            return apology("must provide an integer", 403)

        # ensure positive integer for shares
        elif int(request.form.get("shares")) < 1:
            return apology("must provide positive integer for shares", 403)

        # ensure valid symbol was submitted
        stock_to_buy = lookup(request.form.get("symbol"))
        if stock_to_buy is None:
            return apology("Symbol not found", 404)

        # calculate total price of shares
        shares = int(request.form.get("shares"))
        price_per_share = float(stock_to_buy["price"])
        total = price_per_share * shares

        # identify user info
        user_info = db.execute("SELECT * FROM users WHERE id = :user_id", user_id=session["user_id"])

        # determine if user can afford the stock shares
        cash = user_info[0]["cash"]
        if cash < total:
            return apology("not enough cash to buy", 403)

        # calculate cash balance after purchasing stock shares
        else:
            cash -= total

        # update user cash balance
        db.execute("UPDATE users SET cash = :cash WHERE id = :user_id", cash=cash, user_id=session["user_id"])

        # insert record into history table
        symbol = stock_to_buy["symbol"]
        name = stock_to_buy["name"]

        db.execute("INSERT INTO history (user_id, symbol, name, price, shares, total) VALUES (:user_id, :symbol, :name, :price, :shares, :total)",
        user_id=session["user_id"], symbol=symbol, name=name, price=price_per_share, shares=shares, total=total)

        # redirect user to homepage after buying stocks
        flash("Bought")
        return redirect("/")

    # display buy page when request via GET method
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # query each transaction in history for particular user
    rows = db.execute("SELECT symbol, shares, price, time FROM history WHERE user_id = :user_id ORDER BY time", user_id=session["user_id"])

    records = []
    for record in rows:
        # store table data in dictionaries
        temp = {
            "symbol": record["symbol"],
            "shares": record["shares"],
            "price": usd(record["price"]),
            "transacted": record["time"]
        }

        records.append(temp)

    return render_template("history.html", records=records)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        flash("Logged in successfully")
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/reload", methods=["GET", "POST"])
@login_required
def reload():
    """ reload user cash in account """
    if request.method == "POST":

        if not request.form.get("cash"):
            return apology("must provide amount of cash", 403)

        elif float(request.form.get("cash")) <= 0:
            return apology("must provide positive number", 403)

        rows = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])
        before = rows[0]["cash"]
        after = before + float(request.form.get("cash"))

        # update user cash after reloading
        db.execute("UPDATE users SET cash = :cash WHERE id = :user_id", cash=after, user_id=session["user_id"])

        flash("Reloaded successfully")
        return redirect("/")

    else:
        return render_template("reload.html")

@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":

        # ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide symbol", 403)

        # lookup return a dictionary
        stock_info = lookup(request.form.get("symbol"))

        # handle stock not found
        if stock_info is None:
            return apology("Symbol not found", 404)

        # return search result for the stock symbol
        else:
            name = stock_info["name"]
            price = usd(stock_info["price"])
            symbol = stock_info["symbol"]

            flash("Success")
            return render_template("quoted.html", name=name, price=price, symbol=symbol)

    # display quote page if request via GET method
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # ensure confirmed password was submitted
        elif not request.form.get("confirmation"):
            return apology("must confirm your password", 403)

        # ensure confirmed password is the same
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("confirmed password must match the password", 403)

        # ensure no duplicate username :username is a placeholder
        user_name = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))
        if len(user_name) != 0:
            return apology("username already exists", 403)

        # store hash generated instead of password in database
        hash_password = generate_password_hash(request.form.get("password"))

        # register user in database
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", username=request.form.get("username"), hash=hash_password)

        # redirect user to home page
        flash("Registration success")
        return redirect("/")

    # display the register page when user request via GET method
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":

        # ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide symbol", 403)

        # ensure no. of shares was submitted
        elif not request.form.get("shares"):
            return apology("must provide no. of shares", 403)

        elif not request.form.get("shares").isdigit():
            return apology("must provide an integer", 403)

        # ensure positive integer for no. of share
        elif int(request.form.get("shares")) < 1:
            return apology("must provide positive integer", 403)

        # ensure user own the stock or has enough shares to sell
        stock_to_sell = db.execute("SELECT symbol, SUM(shares) AS holdings FROM history WHERE user_id = :user_id AND symbol = :symbol GROUP BY symbol", user_id=session["user_id"], symbol=request.form.get("symbol"))
        if stock_to_sell is None or stock_to_sell[0]["holdings"] == 0:
            return apology("Must provide stock you own", 403)

        elif int(request.form.get("shares")) > stock_to_sell[0]["holdings"]:
            return apology("you dont have enough shares to sell", 403)

        # get the info of the share on IEX
        stock_info = lookup(request.form.get("symbol"))

        # calculate the total selling price of stock
        shares = int(request.form.get("shares"))
        price_per_share = float(stock_info["price"])
        total = price_per_share * shares

        # update balance cash after selling stock
        user_info = db.execute("SELECT * FROM users WHERE id = :user_id", user_id=session["user_id"])
        cash = user_info[0]["cash"]
        cash += total
        db.execute("UPDATE users SET cash = :cash WHERE id = :user_id", cash=cash, user_id=session["user_id"])

        # insert transaction into history table
        symbol = stock_info["symbol"]
        name = stock_info["name"]
        db.execute("INSERT INTO history (user_id, symbol, name, price, shares, total) VALUES (:user_id, :symbol, :name, :price, :shares, :total)",
        user_id=session["user_id"], symbol=symbol, name=name, price=price_per_share, shares=(-shares), total=total)

        # redirect user to homepage
        flash("Sold")
        return redirect("/")

    # display sell page when user request via GET method
    else:
        return render_template("sell.html")


@app.route("/password", methods=["GET", "POST"])
@login_required
def change_password():
    """Change uaer password"""
    if request.method == "POST":

        if not request.form.get("password"):
            return apology("must provide password", 403)

        elif not request.form.get("new"):
            return apology("must provide new password", 403)

        elif not request.form.get("confirmed"):
            return apology("must confirmed new password", 403)

        old_password = request.form.get("password")
        rows = db.execute("SELECT hash FROM users WHERE id = :user_id", user_id=session["user_id"])
        hash_password = rows[0]["hash"]

        # ensure user enter old password
        if not check_password_hash(hash_password, old_password):
            return apology("must provide current password", 403)

        # ensure new password is different
        new_password = request.form.get("new")
        if old_password == new_password:
            return apology("new password must be different", 403)

        # ensure new password is confirmed
        confirmed_password = request.form.get("confirmed")
        if new_password != confirmed_password:
            return apology("must confirmed new password", 403)

        # update hash password
        hash_password = generate_password_hash(new_password)
        db.execute("UPDATE users SET hash = :hash_password WHERE id = :user_id", hash_password=hash_password, user_id=session["user_id"])

        flash("Password changed")
        return redirect("/")

    else:
        return render_template("password.html")

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
